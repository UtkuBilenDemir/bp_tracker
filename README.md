# BP Tracker

> A personal experiment in human–AI collaboration, built entirely through conversation with **Claude Code**.

This is a lightweight, local blood pressure tracking system. Drop a photo of your BP monitor into a folder — the app reads the display, logs the values, and renders them in a live dashboard. No manual transcription, no cloud services, no subscriptions beyond an Anthropic API key.

---

## What this is

This project started as a test: *how far can you get building a real, useful tool by just talking to an AI?*

The answer, it turns out, is pretty far. Every line of code, every design decision — the folder watcher, the vision extraction, the colour-coded dashboard, the gitignore, the environment setup — was written by [Claude Code](https://claude.ai/claude-code) through a back-and-forth conversation. No manual coding required.

The tool itself is genuinely useful: it watches a folder for photos of a blood pressure monitor, uses Claude's vision API to extract the readings automatically, logs everything to a CSV you can edit by hand, and displays a clean Plotly/Dash dashboard with clinical reference zones and hover annotations.

---

## How it works

```
📷 Photo dropped into watch_folder/
        ↓
🔍 watcher.py detects the new file
        ↓
🤖 Claude vision API reads the monitor display
   → systolic, diastolic, heart rate, confidence, comment
        ↓
📅 Timestamp extracted from photo EXIF data
   (never silently falls back to system time)
        ↓
📄 New row appended to data/readings.csv
        ↓
📊 dashboard.py auto-refreshes with the new reading
```

---

## Features

- **Automatic reading extraction** via Claude vision — no typing numbers manually
- **EXIF-first timestamps** — uses when the photo was actually taken, not when it was processed
- **Duplicate detection** — same photo dropped twice is silently skipped (hash-based)
- **Colour-coded BP zones** — green / yellow / red bands based on clinical thresholds
- **Baseline reference lines** — compare every reading against your personal baseline
- **Dose tracking** — mark readings where medication was taken; shown as a distinct marker on the chart
- **AI hover tooltips** — each data point carries a short clinical comment generated at extraction time
- **Hand-editable CSV** — the data store is plain text; add, edit or delete rows freely
- **Auto-refresh dashboard** — polls every 15 seconds, no page reload needed

---

## Project structure

```
bp-tracker/
├── watch_folder/           ← drop photos here
│   └── .gitkeep
├── data/
│   ├── readings.csv        ← your data (gitignored)
│   ├── readings.example.csv
│   ├── errors.log          ← extraction failures (gitignored)
│   └── .gitkeep
├── config.py               ← all settings in one place
├── watcher.py              ← folder watcher + vision extraction
├── dashboard.py            ← Plotly/Dash visualisation
├── pyproject.toml          ← dependencies (managed by uv)
├── uv.lock                 ← exact pinned versions
├── .env.example            ← API key template
└── .python-version         ← Python 3.12
```

---

## Setup

### 1. Clone and install

This project uses [uv](https://github.com/astral-sh/uv) for environment management — fast, reproducible, no manual venv needed.

```bash
git clone git@github.com:UtkuBilenDemir/bp_tracker.git
cd bp_tracker

# Install uv if you don't have it
brew install uv          # macOS
# or: pip install uv

# Create virtualenv and install all dependencies at pinned versions
uv sync
```

### 2. Add your API key

The watcher uses the [Anthropic API](https://console.anthropic.com) for vision extraction. New accounts receive $5 in free credits — sufficient for months of daily readings at this scale.

```bash
cp .env.example .env
```

Open `.env` and replace the placeholder:

```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
```

> Your key never leaves this file. `.env` is gitignored and will never be committed.

### 3. Configure your baseline

Open `config.py` and update the baseline values to match your own:

```python
BASELINE_SYSTOLIC  = 111   # mmHg
BASELINE_DIASTOLIC = 63    # mmHg
BASELINE_HR        = 60    # bpm
```

These appear as reference lines on the dashboard and inform the AI's hover comments.

---

## Usage

### Start the watcher

In one terminal, run:

```bash
uv run python watcher.py
```

Then drop a photo of your blood pressure monitor into `watch_folder/`. The watcher will:

1. Detect the new file
2. Extract the timestamp from EXIF data (or ask you to enter it manually if missing)
3. Send the image to Claude for reading extraction
4. Ask whether a dose was taken and at what time
5. Append a new row to `data/readings.csv`

### Start the dashboard

In a second terminal:

```bash
uv run python dashboard.py
```

Open **http://localhost:8050** in your browser. The dashboard auto-refreshes every 15 seconds.

---

## Dashboard reference

| Element | Meaning |
|---|---|
| Red line | Systolic pressure |
| Purple line | Diastolic pressure |
| Green line | Heart rate (lower chart) |
| ◆ Diamond marker | Reading taken with a dose |
| ● Circle marker | Reading taken without a dose |
| Green band | Normal range |
| Yellow band | Elevated (>130/85 mmHg) |
| Red band | High (>140/90 mmHg) |
| Dotted lines | Your personal baseline |
| Hover tooltip | All values + AI clinical comment |

---

## CSV format

The data file is plain CSV — open it in Excel, Numbers, or any text editor. You can add or correct entries by hand at any time.

```
timestamp,systolic,diastolic,heart_rate,dose_taken,dose_time,photo_filename,ai_comment
2026-02-25 08:14:00,111,63,60,False,,,Baseline reading. BP and HR well within normal range.
2026-03-01 09:02:00,118,68,65,True,08:30,reading_day1_morning.jpg,Mild elevation on day one...
```

See `data/readings.example.csv` for a fuller example.

---

## A note on privacy

Health data is sensitive. This project is designed with that in mind:

- All data stays **local** — no cloud sync, no external database
- Photos and readings are **gitignored** and never committed
- The API sends images to Anthropic for processing — review their [privacy policy](https://www.anthropic.com/privacy) if that matters for your use case
- The `.env` file with your API key is gitignored

---

## Built with

- [Anthropic Claude](https://anthropic.com) — vision extraction + AI comments
- [Plotly / Dash](https://dash.plotly.com) — interactive dashboard
- [Watchdog](https://github.com/gorakhargosh/watchdog) — filesystem monitoring
- [Pillow](https://python-pillow.org) — EXIF extraction
- [pandas](https://pandas.pydata.org) — CSV handling
- [uv](https://github.com/astral-sh/uv) — environment management

---

*Built through conversation with [Claude Code](https://claude.ai/claude-code) — Anthropic's AI coding assistant.*
