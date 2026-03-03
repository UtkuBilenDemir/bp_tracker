#!/usr/bin/env python3
"""
Watches watch_folder/ for new BP monitor photos.
Extracts readings via Claude vision API and appends to data/readings.csv.
"""

import base64
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic
from PIL import Image, ExifTags
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}


def log_error(message: str) -> None:
    timestamp = datetime.now().isoformat(sep=" ", timespec="seconds")
    with open(config.ERROR_LOG_PATH, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"  ERROR: {message}", file=sys.stderr)


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_seen_hashes() -> set[str]:
    """Collect hashes of photos already recorded in the CSV."""
    seen = set()
    csv_path = Path(config.CSV_PATH)
    if not csv_path.exists():
        return seen
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            filename = row.get("photo_filename", "")
            full_path = Path(config.WATCH_FOLDER) / filename
            if full_path.exists():
                try:
                    seen.add(file_hash(str(full_path)))
                except OSError:
                    pass
    return seen


def get_exif_timestamp(path: str) -> datetime | None:
    """Return DateTimeOriginal or DateTime from EXIF, or None."""
    try:
        img = Image.open(path)
        exif_data = img._getexif()
        if not exif_data:
            return None
        tag_map = {v: k for k, v in ExifTags.TAGS.items()}
        for tag_name in ("DateTimeOriginal", "DateTime"):
            tag_id = tag_map.get(tag_name)
            if tag_id and tag_id in exif_data:
                raw = exif_data[tag_id]
                return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def prompt_manual_timestamp() -> datetime:
    """Ask the user to enter a timestamp when EXIF is unavailable."""
    print("\n  No EXIF timestamp found in this photo.")
    print("  Enter the date/time when the reading was taken.")
    while True:
        raw = input("  Format YYYY-MM-DD HH:MM  → ").strip()
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M")
        except ValueError:
            print("  Invalid format — try again.")


def extract_reading_via_vision(image_path: str) -> dict:
    """
    Send the image to Claude vision and return parsed JSON with:
    systolic, diastolic, heart_rate, confidence, any_warnings, short_comment
    Raises ValueError on failure or low confidence.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    suffix = Path(image_path).suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }
    media_type = media_type_map.get(suffix, "image/jpeg")

    prompt = f"""You are reading a blood pressure monitor display from a photo.

Extract the values shown and return ONLY valid JSON — no prose, no markdown fences.

Required fields:
- systolic       (integer mmHg)
- diastolic      (integer mmHg)
- heart_rate     (integer bpm)
- confidence     ("low" | "medium" | "high")
- any_warnings   (string — e.g. "irregular heartbeat symbol detected", or "")
- short_comment  (1-2 sentences, clinically grounded, friendly tone.
                  Patient baseline is {config.BASELINE_SYSTOLIC}/{config.BASELINE_DIASTOLIC} mmHg,
                  HR {config.BASELINE_HR} bpm. Note if elevated vs baseline.)

If you cannot read a value clearly, set confidence to "low" and explain in any_warnings."""

    response = client.messages.create(
        model=config.VISION_MODEL,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    raw = response.content[0].text.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Vision API returned non-JSON: {raw[:200]}") from e

    if result.get("confidence") == "low":
        raise ValueError(
            f"Low confidence extraction: {result.get('any_warnings', 'no details')}"
        )

    return result


def append_to_csv(row: dict) -> None:
    csv_path = Path(config.CSV_PATH)
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=config.CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def ask_dose() -> tuple[bool, str]:
    """Ask whether a dose was taken and at what time."""
    answer = input("  Was a dose taken today? (y/n): ").strip().lower()
    if answer == "y":
        dose_time = input("  What time? (HH:MM, or leave blank if unknown): ").strip()
        return True, dose_time
    return False, ""


# ---------------------------------------------------------------------------
# Watchdog handler
# ---------------------------------------------------------------------------

class PhotoHandler(FileSystemEventHandler):
    def __init__(self, seen_hashes: set[str]):
        self.seen_hashes = seen_hashes

    def on_created(self, event):
        if event.is_directory:
            return
        path = event.src_path
        if Path(path).suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        # Brief pause — some apps write files non-atomically
        time.sleep(1)
        process_photo(path, self.seen_hashes)


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_photo(path: str, seen_hashes: set[str]) -> None:
    filename = Path(path).name
    print(f"\n{'─' * 50}")
    print(f"  New photo detected: {filename}")

    # Duplicate check
    h = file_hash(path)
    if h in seen_hashes:
        print("  Duplicate — already recorded. Skipping.")
        return
    seen_hashes.add(h)

    # Timestamp
    ts = get_exif_timestamp(path)
    if ts:
        print(f"  Timestamp from EXIF: {ts}")
    else:
        ts = prompt_manual_timestamp()

    # Vision extraction
    print("  Sending to Claude vision API…")
    try:
        reading = extract_reading_via_vision(path)
    except ValueError as e:
        log_error(f"{filename}: {e}")
        print("  Extraction failed — logged to errors.log. CSV not updated.")
        return

    print(f"  Systolic:   {reading['systolic']} mmHg")
    print(f"  Diastolic:  {reading['diastolic']} mmHg")
    print(f"  Heart rate: {reading['heart_rate']} bpm")
    print(f"  Confidence: {reading['confidence']}")
    if reading.get("any_warnings"):
        print(f"  Warnings:   {reading['any_warnings']}")
    print(f"  Comment:    {reading['short_comment']}")

    # Dose info
    dose_taken, dose_time = ask_dose()

    # Write CSV
    row = {
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "systolic": reading["systolic"],
        "diastolic": reading["diastolic"],
        "heart_rate": reading["heart_rate"],
        "dose_taken": dose_taken,
        "dose_time": dose_time,
        "photo_filename": filename,
        "ai_comment": reading["short_comment"],
    }
    append_to_csv(row)
    print("  Saved to CSV.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if not config.ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    watch_path = Path(config.WATCH_FOLDER)
    watch_path.mkdir(parents=True, exist_ok=True)
    Path(config.CSV_PATH).parent.mkdir(parents=True, exist_ok=True)

    seen_hashes = load_seen_hashes()
    print(f"Watching {watch_path.resolve()} for new photos…")
    print("Drop a BP monitor photo into the folder to record a reading.")
    print("Press Ctrl+C to stop.\n")

    handler = PhotoHandler(seen_hashes)
    observer = Observer()
    observer.schedule(handler, str(watch_path), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
