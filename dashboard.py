#!/usr/bin/env python3
"""
BP Tracker — Plotly/Dash dashboard.

Features:
  - Photo upload → Claude vision → CSV logging
  - Manual entry without a photo
  - Delete last reading (with confirmation)
  - Blood pressure + heart rate charts
  - CSV download
  - User management (add/remove basic-auth users)

Dev:  uv run python dashboard.py
Prod: gunicorn dashboard:server -b 127.0.0.1:8050 --workers 1 --timeout 120
"""

import base64
import csv as csv_mod
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import anthropic
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, callback, dcc, html, no_update
from passlib.apache import HtpasswdFile
from PIL import Image, ExifTags

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

import config

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Dash(__name__, title="BP Tracker")
server = app.server

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

CARD = {
    "background": "#fff",
    "borderRadius": "12px",
    "padding": "24px",
    "marginBottom": "20px",
    "boxShadow": "0 1px 4px rgba(0,0,0,0.08)",
}
LABEL = {"fontSize": "13px", "color": "#666", "marginBottom": "4px", "display": "block"}
INPUT_STYLE = {
    "width": "100%",
    "padding": "8px 12px",
    "border": "1px solid #ddd",
    "borderRadius": "8px",
    "fontSize": "14px",
    "boxSizing": "border-box",
}
BTN = {
    "padding": "10px 20px",
    "borderRadius": "8px",
    "border": "none",
    "cursor": "pointer",
    "fontSize": "14px",
    "fontWeight": "500",
}
BTN_PRIMARY = {**BTN, "background": "#2c3e50", "color": "#fff"}
BTN_SECONDARY = {**BTN, "background": "#f0f0f0", "color": "#333"}
BTN_DANGER = {**BTN, "background": "#e74c3c", "color": "#fff"}
BTN_WARN = {**BTN, "background": "#e67e22", "color": "#fff"}


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

app.layout = html.Div(
    style={
        "fontFamily": "system-ui, -apple-system, sans-serif",
        "maxWidth": "900px",
        "margin": "0 auto",
        "padding": "24px 16px",
        "background": "#f5f6fa",
        "minHeight": "100vh",
    },
    children=[

        dcc.Store(id="confirm-delete-store", data=False),

        # ── Header ──────────────────────────────────────────────────────────
        html.Div(style=CARD, children=[
            html.Div(style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start"}, children=[
                html.Div([
                    html.H1("BP Tracker", style={"margin": "0 0 4px", "fontSize": "24px"}),
                    html.P(
                        [
                            f"Baseline: {config.BASELINE_SYSTOLIC}/{config.BASELINE_DIASTOLIC} mmHg  ·  "
                            f"HR {config.BASELINE_HR} bpm  ·  ",
                            html.Span(f"Dose: {config.CURRENT_DOSE_MG} mg/day",
                                      style={"color": "#e67e22", "fontWeight": "500"}),
                        ],
                        style={"margin": 0, "color": "#888", "fontSize": "14px"},
                    ),
                ]),
                html.Button("⬇ Download CSV", id="btn-download", style=BTN_SECONDARY),
            ]),
            dcc.Download(id="download-csv"),
        ]),

        # ── Add Reading ──────────────────────────────────────────────────────
        html.Div(style=CARD, children=[
            html.H2("Add Reading", style={"margin": "0 0 12px", "fontSize": "18px"}),

            dcc.RadioItems(
                id="entry-mode",
                options=[
                    {"label": "  📷  From photo", "value": "photo"},
                    {"label": "  ✏️  Enter manually", "value": "manual"},
                ],
                value="photo",
                inline=True,
                style={"fontSize": "14px", "marginBottom": "20px"},
            ),

            # ── Photo mode ──────────────────────────────────────────────────
            html.Div(id="photo-section", children=[
                dcc.Upload(
                    id="upload-photo",
                    children=html.Div([
                        html.Span("📷  ", style={"fontSize": "24px"}),
                        html.Span("Drop a photo here or "),
                        html.A("browse", style={"color": "#2980b9", "cursor": "pointer"}),
                    ]),
                    style={
                        "border": "2px dashed #ccc",
                        "borderRadius": "10px",
                        "padding": "32px",
                        "textAlign": "center",
                        "cursor": "pointer",
                        "marginBottom": "16px",
                        "color": "#888",
                    },
                    accept="image/*",
                ),
                html.Div(style={"flex": "2 1 200px", "marginBottom": "16px"}, children=[
                    html.Label("Override timestamp (if no EXIF)", style=LABEL),
                    dcc.Input(id="manual-ts", type="text",
                              placeholder="YYYY-MM-DD HH:MM  (optional)", style=INPUT_STYLE),
                ]),
            ]),

            # ── Manual mode ─────────────────────────────────────────────────
            html.Div(id="manual-section", style={"display": "none"}, children=[
                html.Div(style={"display": "flex", "gap": "16px", "marginBottom": "16px", "flexWrap": "wrap"}, children=[
                    html.Div(style={"flex": "2 1 180px"}, children=[
                        html.Label("Timestamp (YYYY-MM-DD HH:MM)", style=LABEL),
                        dcc.Input(id="manual-timestamp", type="text",
                                  placeholder="e.g. 2026-03-04 08:30", style=INPUT_STYLE),
                    ]),
                    html.Div(style={"flex": "1 1 80px"}, children=[
                        html.Label("Systolic", style=LABEL),
                        dcc.Input(id="manual-systolic", type="number", placeholder="e.g. 118", style=INPUT_STYLE),
                    ]),
                    html.Div(style={"flex": "1 1 80px"}, children=[
                        html.Label("Diastolic", style=LABEL),
                        dcc.Input(id="manual-diastolic", type="number", placeholder="e.g. 72", style=INPUT_STYLE),
                    ]),
                    html.Div(style={"flex": "1 1 80px"}, children=[
                        html.Label("Heart rate", style=LABEL),
                        dcc.Input(id="manual-hr", type="number", placeholder="e.g. 65", style=INPUT_STYLE),
                    ]),
                ]),
                html.Div(style={"marginBottom": "16px"}, children=[
                    html.Label("Note (optional)", style=LABEL),
                    dcc.Input(id="manual-comment", type="text",
                              placeholder="Any observations...", style=INPUT_STYLE),
                ]),
            ]),

            # ── Dose fields — shared between both modes ──────────────────────
            html.Div(style={"display": "flex", "gap": "16px", "marginBottom": "16px",
                            "flexWrap": "wrap", "marginTop": "8px"}, children=[
                html.Div(style={"flex": "0 0 auto"}, children=[
                    html.Label("Dose taken today?", style=LABEL),
                    dcc.Checklist(
                        id="dose-taken",
                        options=[{"label": "  Yes", "value": "yes"}],
                        value=[],
                        style={"fontSize": "14px", "paddingTop": "8px"},
                    ),
                ]),
                html.Div(style={"flex": "1 1 90px"}, children=[
                    html.Label("Dose (mg)", style=LABEL),
                    dcc.Input(id="dose-mg", type="number", value=config.CURRENT_DOSE_MG, min=0,
                              style={**INPUT_STYLE, "maxWidth": "100px"}),
                ]),
                html.Div(style={"flex": "1 1 120px"}, children=[
                    html.Label("Dose time (HH:MM)", style=LABEL),
                    dcc.Input(id="dose-time", type="text", placeholder="e.g. 08:30",
                              style={**INPUT_STYLE, "maxWidth": "140px"}),
                ]),
                html.Div(style={"flex": "0 0 auto", "paddingTop": "20px"}, children=[
                    html.Button("Process Reading", id="btn-submit", style={**BTN_PRIMARY, "display": "inline-block"}),
                    html.Button("Save Reading", id="btn-manual-submit", style={**BTN_PRIMARY, "display": "none"}),
                ]),
            ]),

            html.Div(id="upload-status", style={"marginTop": "12px", "fontSize": "14px"}),
            html.Div(id="manual-status", style={"marginTop": "12px", "fontSize": "14px"}),
        ]),

        # ── Charts ──────────────────────────────────────────────────────────
        html.Div(style=CARD, children=[
            dcc.Graph(id="bp-chart", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD, children=[
            dcc.Graph(id="hr-chart", config={"displayModeBar": False}),
        ]),

        dcc.Interval(id="refresh", interval=15_000, n_intervals=0),

        # ── Data management ──────────────────────────────────────────────────
        html.Div(style=CARD, children=[
            html.H2("Data", style={"margin": "0 0 12px", "fontSize": "18px"}),
            html.Div(id="last-reading-info", style={"fontSize": "14px", "color": "#555", "marginBottom": "12px"}),
            html.Div(style={"display": "flex", "gap": "10px"}, children=[
                html.Button("🗑 Delete Last Reading", id="btn-delete", style=BTN_WARN),
                html.Button("✓ Confirm Delete", id="btn-confirm-delete",
                            style={**BTN_DANGER, "display": "none"}),
            ]),
            html.Div(id="delete-status", style={"marginTop": "10px", "fontSize": "14px"}),
        ]),

        # ── User management ──────────────────────────────────────────────────
        html.Div(style=CARD, children=[
            html.H2("Access", style={"margin": "0 0 16px", "fontSize": "18px"}),
            html.Div(id="users-list", style={"marginBottom": "16px", "fontSize": "14px", "color": "#555"}),
            html.Div(style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "alignItems": "flex-end"}, children=[
                html.Div(style={"flex": "1 1 140px"}, children=[
                    html.Label("Username", style=LABEL),
                    dcc.Input(id="new-username", type="text", placeholder="username", style=INPUT_STYLE),
                ]),
                html.Div(style={"flex": "1 1 140px"}, children=[
                    html.Label("Password", style=LABEL),
                    dcc.Input(id="new-password", type="password", placeholder="password", style=INPUT_STYLE),
                ]),
                html.Div(style={"display": "flex", "gap": "8px"}, children=[
                    html.Button("Add", id="btn-add-user", style=BTN_PRIMARY),
                    html.Button("Remove", id="btn-remove-user", style=BTN_DANGER),
                ]),
            ]),
            html.Div(id="user-status", style={"marginTop": "10px", "fontSize": "13px"}),
        ]),
    ],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    try:
        df = pd.read_csv(config.CSV_PATH, parse_dates=["timestamp"])
    except FileNotFoundError:
        return pd.DataFrame(columns=config.CSV_COLUMNS)
    return df.sort_values("timestamp").reset_index(drop=True)


def get_exif_timestamp(path: str) -> datetime | None:
    try:
        img = Image.open(path)
        exif = img._getexif()
        if not exif:
            return None
        tag_map = {v: k for k, v in ExifTags.TAGS.items()}
        for name in ("DateTimeOriginal", "DateTime"):
            tag_id = tag_map.get(name)
            if tag_id and tag_id in exif:
                return datetime.strptime(exif[tag_id], "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def extract_reading_via_vision(image_path: str) -> dict:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    prompt = f"""You are reading a blood pressure monitor display from a photo.
Return ONLY valid JSON — no prose, no markdown fences.

Fields:
- systolic       (integer mmHg)
- diastolic      (integer mmHg)
- heart_rate     (integer bpm)
- confidence     ("low" | "medium" | "high")
- any_warnings   (string, or "")
- short_comment  (1–2 sentences, friendly, clinically grounded.
                  Baseline is {config.BASELINE_SYSTOLIC}/{config.BASELINE_DIASTOLIC} mmHg,
                  HR {config.BASELINE_HR} bpm. Note if elevated vs baseline.)"""

    response = client.messages.create(
        model=config.VISION_MODEL,
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    raw = response.content[0].text.strip()
    result = json.loads(raw)
    if result.get("confidence") == "low":
        raise ValueError(f"Low confidence: {result.get('any_warnings', '')}")
    return result


def append_to_csv(row: dict) -> None:
    csv_path = Path(config.CSV_PATH)
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv_mod.DictWriter(f, fieldnames=config.CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def bp_zone_shapes(df):
    if df.empty:
        return []
    x0, x1 = df["timestamp"].min(), df["timestamp"].max()
    return [
        dict(type="rect", xref="x", yref="y", x0=x0, x1=x1, y0=0,
             y1=config.ELEVATED_SYSTOLIC, fillcolor="rgba(72,199,142,0.08)", line_width=0, layer="below"),
        dict(type="rect", xref="x", yref="y", x0=x0, x1=x1,
             y0=config.ELEVATED_SYSTOLIC, y1=config.HIGH_SYSTOLIC,
             fillcolor="rgba(255,221,87,0.12)", line_width=0, layer="below"),
        dict(type="rect", xref="x", yref="y", x0=x0, x1=x1,
             y0=config.HIGH_SYSTOLIC, y1=220, fillcolor="rgba(255,99,71,0.10)", line_width=0, layer="below"),
    ]


def bp_zone_annotations():
    return [
        dict(xref="paper", yref="y", x=1.01, y=config.ELEVATED_SYSTOLIC,
             text="Elevated", showarrow=False, font=dict(size=10, color="#b8a100"), xanchor="left"),
        dict(xref="paper", yref="y", x=1.01, y=config.HIGH_SYSTOLIC,
             text="High", showarrow=False, font=dict(size=10, color="#c0392b"), xanchor="left"),
    ]


# ---------------------------------------------------------------------------
# Callbacks — toggle entry mode
# ---------------------------------------------------------------------------

@callback(
    Output("photo-section", "style"),
    Output("manual-section", "style"),
    Output("btn-submit", "style"),
    Output("btn-manual-submit", "style"),
    Input("entry-mode", "value"),
)
def toggle_mode(mode):
    if mode == "photo":
        return {}, {"display": "none"}, BTN_PRIMARY, {**BTN_PRIMARY, "display": "none"}
    return {"display": "none"}, {}, {**BTN_PRIMARY, "display": "none"}, BTN_PRIMARY


# ---------------------------------------------------------------------------
# Callbacks — charts
# ---------------------------------------------------------------------------

@callback(
    Output("bp-chart", "figure"),
    Output("hr-chart", "figure"),
    Input("refresh", "n_intervals"),
    Input("upload-status", "children"),
    Input("manual-status", "children"),
    Input("delete-status", "children"),
)
def update_charts(_n, _upload, _manual, _delete):
    df = load_data()

    fig_bp = go.Figure()
    if not df.empty:
        fig_bp.update_layout(shapes=bp_zone_shapes(df), annotations=bp_zone_annotations())
        for y, label, color in [
            (config.BASELINE_SYSTOLIC, f"Baseline sys {config.BASELINE_SYSTOLIC}", "#2980b9"),
            (config.BASELINE_DIASTOLIC, f"Baseline dia {config.BASELINE_DIASTOLIC}", "#8e44ad"),
        ]:
            fig_bp.add_hline(y=y, line_dash="dot", line_color=color, opacity=0.5,
                             annotation_text=label, annotation_position="bottom right")

        hr_str = lambda r: f"{int(r['heart_rate'])} bpm" if pd.notna(r.get("heart_rate")) else "HR unknown"
        hover = df.apply(lambda r: (
            f"<b>{r['timestamp'].strftime('%d %b %Y  %H:%M')}</b><br>"
            f"BP: {r['systolic']}/{r['diastolic']} mmHg<br>"
            f"HR: {hr_str(r)}<br>"
            + (f"Dose: {int(r['dose_mg'])} mg  ·  {r['dose_time']}<br>"
               if r.get("dose_taken") else "No dose<br>")
            + f"<i>{r.get('ai_comment', '')}</i>"
        ), axis=1)

        symbols = df["dose_taken"].map(lambda d: "diamond" if d else "circle")
        dose_series = df["dose_mg"].fillna(0)
        for i in range(1, len(df)):
            if dose_series.iloc[i] != dose_series.iloc[i - 1]:
                fig_bp.add_vline(
                    x=df["timestamp"].iloc[i].timestamp() * 1000,
                    line_dash="dash", line_color="#e67e22", opacity=0.6,
                    annotation_text=f"{int(dose_series.iloc[i])} mg",
                    annotation_position="top",
                    annotation_font=dict(size=11, color="#e67e22"),
                )

        for col, name, color in [("systolic", "Systolic", "#e74c3c"), ("diastolic", "Diastolic", "#8e44ad")]:
            fig_bp.add_trace(go.Scatter(
                x=df["timestamp"], y=df[col], mode="lines+markers", name=name,
                line=dict(color=color, width=2),
                marker=dict(size=9, symbol=symbols),
                hovertext=hover, hoverinfo="text",
            ))

    fig_bp.update_layout(
        title="Blood Pressure over Time", yaxis_title="mmHg",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified", plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(r=80), height=360,
    )
    fig_bp.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
    fig_bp.update_yaxes(showgrid=True, gridcolor="#f0f0f0", range=[40, 200])

    fig_hr = go.Figure()
    if not df.empty:
        fig_hr.add_hline(y=config.BASELINE_HR, line_dash="dot", line_color="#27ae60", opacity=0.5,
                         annotation_text=f"Baseline HR {config.BASELINE_HR}", annotation_position="bottom right")
        fig_hr.add_trace(go.Scatter(
            x=df["timestamp"], y=df["heart_rate"], mode="lines+markers", name="Heart rate",
            line=dict(color="#27ae60", width=2),
            marker=dict(size=9, symbol=df["dose_taken"].map(lambda d: "diamond" if d else "circle")),
            hovertemplate="%{x|%d %b %H:%M}<br>HR: %{y} bpm<extra></extra>",
        ))

    fig_hr.update_layout(
        title="Heart Rate over Time", yaxis_title="bpm",
        hovermode="x unified", plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(r=80), height=240,
    )
    fig_hr.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
    fig_hr.update_yaxes(showgrid=True, gridcolor="#f0f0f0", range=[40, 140])

    return fig_bp, fig_hr


# ---------------------------------------------------------------------------
# Callbacks — photo upload
# ---------------------------------------------------------------------------

@callback(
    Output("upload-status", "children"),
    Input("btn-submit", "n_clicks"),
    State("upload-photo", "contents"),
    State("upload-photo", "filename"),
    State("dose-taken", "value"),
    State("dose-mg", "value"),
    State("dose-time", "value"),
    State("manual-ts", "value"),
    prevent_initial_call=True,
)
def process_reading(_, contents, filename, dose_taken, dose_mg, dose_time, manual_ts):
    if not contents:
        return "⚠️ Please select a photo first."

    # Duplicate check by filename
    if filename:
        df_existing = load_data()
        if not df_existing.empty and filename in df_existing["photo_filename"].values:
            return f"⚠️ '{filename}' has already been recorded. Use manual entry to add another reading."

    _, content_string = contents.split(",", 1)
    image_bytes = base64.b64decode(content_string)
    suffix = ".heic" if filename and filename.lower().endswith(".heic") else ".jpg"

    tmp_orig = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_jpeg = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    try:
        tmp_orig.write(image_bytes)
        tmp_orig.flush()
        tmp_orig.close()

        img = Image.open(tmp_orig.name)
        img.convert("RGB").save(tmp_jpeg.name, "JPEG", quality=90)
        tmp_jpeg.close()

        ts = get_exif_timestamp(tmp_orig.name)
        if ts:
            ts_source = f"EXIF ({ts.strftime('%d %b %Y %H:%M')})"
        elif manual_ts and manual_ts.strip():
            try:
                ts = datetime.strptime(manual_ts.strip(), "%Y-%m-%d %H:%M")
                ts_source = "manual entry"
            except ValueError:
                return "⚠️ Invalid timestamp format. Use YYYY-MM-DD HH:MM"
        else:
            return "⚠️ No EXIF timestamp found. Enter date/time in the override field."

        try:
            reading = extract_reading_via_vision(tmp_jpeg.name)
        except Exception as e:
            return f"⚠️ Vision extraction failed: {e}"

        append_to_csv({
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "systolic": reading["systolic"],
            "diastolic": reading["diastolic"],
            "heart_rate": reading["heart_rate"],
            "dose_taken": bool(dose_taken),
            "dose_mg": dose_mg if dose_taken else 0,
            "dose_time": dose_time or "",
            "photo_filename": filename or "",
            "ai_comment": reading.get("short_comment", ""),
        })

        warnings = f"  ⚠️ {reading['any_warnings']}" if reading.get("any_warnings") else ""
        return (f"✅ Saved — {reading['systolic']}/{reading['diastolic']} mmHg, "
                f"HR {reading['heart_rate']} bpm  ·  {ts_source}{warnings}")

    except Exception as e:
        return f"⚠️ Unexpected error: {e}"
    finally:
        for p in (tmp_orig.name, tmp_jpeg.name):
            try:
                os.unlink(p)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Callbacks — manual entry
# ---------------------------------------------------------------------------

@callback(
    Output("manual-status", "children"),
    Input("btn-manual-submit", "n_clicks"),
    State("manual-timestamp", "value"),
    State("manual-systolic", "value"),
    State("manual-diastolic", "value"),
    State("manual-hr", "value"),
    State("dose-taken", "value"),
    State("dose-mg", "value"),
    State("dose-time", "value"),
    State("manual-comment", "value"),
    prevent_initial_call=True,
)
def save_manual_reading(_, timestamp, systolic, diastolic, hr, dose_taken, dose_mg, dose_time, comment):
    if not all([timestamp, systolic, diastolic, hr]):
        return "⚠️ Timestamp, systolic, diastolic and heart rate are all required."
    try:
        ts = datetime.strptime(timestamp.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return "⚠️ Invalid timestamp format. Use YYYY-MM-DD HH:MM"

    append_to_csv({
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "systolic": int(systolic),
        "diastolic": int(diastolic),
        "heart_rate": int(hr),
        "dose_taken": bool(dose_taken),
        "dose_mg": dose_mg if dose_taken else 0,
        "dose_time": dose_time or "",
        "photo_filename": "",
        "ai_comment": comment or "",
    })
    return f"✅ Saved — {int(systolic)}/{int(diastolic)} mmHg, HR {int(hr)} bpm  ·  manual entry"


# ---------------------------------------------------------------------------
# Callbacks — delete last reading
# ---------------------------------------------------------------------------

@callback(
    Output("last-reading-info", "children"),
    Output("btn-confirm-delete", "style"),
    Output("confirm-delete-store", "data"),
    Input("btn-delete", "n_clicks"),
    Input("delete-status", "children"),
    Input("refresh", "n_intervals"),
    prevent_initial_call=False,
)
def prepare_delete(n_clicks, _status, _n):
    from dash import ctx
    df = load_data()
    if df.empty:
        return "No readings yet.", {**BTN_DANGER, "display": "none"}, False

    last = df.iloc[-1]
    hr = f"HR {int(last['heart_rate'])} bpm" if pd.notna(last.get("heart_rate")) else ""
    info = (f"Last reading: {last['timestamp'].strftime('%d %b %Y  %H:%M')}  ·  "
            f"{int(last['systolic'])}/{int(last['diastolic'])} mmHg  ·  {hr}")

    if ctx.triggered_id == "btn-delete" and n_clicks:
        return info, BTN_DANGER, True

    return info, {**BTN_DANGER, "display": "none"}, False


@callback(
    Output("delete-status", "children"),
    Input("btn-confirm-delete", "n_clicks"),
    prevent_initial_call=True,
)
def confirm_delete(_):
    df = load_data()
    if df.empty:
        return "⚠️ Nothing to delete."
    last = df.iloc[-1]
    df = df.iloc[:-1]
    df.to_csv(config.CSV_PATH, index=False)
    return (f"🗑 Deleted: {last['timestamp'].strftime('%d %b %Y %H:%M')}  ·  "
            f"{int(last['systolic'])}/{int(last['diastolic'])} mmHg")


# ---------------------------------------------------------------------------
# Callbacks — CSV download
# ---------------------------------------------------------------------------

@callback(
    Output("download-csv", "data"),
    Input("btn-download", "n_clicks"),
    prevent_initial_call=True,
)
def download_csv(_):
    return dcc.send_file(config.CSV_PATH, filename="bp_readings.csv")


# ---------------------------------------------------------------------------
# Callbacks — user management
# ---------------------------------------------------------------------------

def load_htpasswd() -> HtpasswdFile:
    path = config.HTPASSWD_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if not Path(path).exists():
        ht = HtpasswdFile(path, new=True)
        ht.save()
    return HtpasswdFile(path, new=False)


@callback(
    Output("users-list", "children"),
    Input("refresh", "n_intervals"),
    Input("user-status", "children"),
)
def refresh_users_list(_n, _status):
    try:
        ht = load_htpasswd()
        users = ht.users()
        return f"Current users: {', '.join(sorted(users))}" if users else "No users configured."
    except Exception:
        return "Could not load user list."


@callback(
    Output("user-status", "children"),
    Input("btn-add-user", "n_clicks"),
    Input("btn-remove-user", "n_clicks"),
    State("new-username", "value"),
    State("new-password", "value"),
    prevent_initial_call=True,
)
def manage_users(_, __, username, password):
    from dash import ctx
    if not username or not username.strip():
        return "⚠️ Username is required."
    username = username.strip()
    ht = load_htpasswd()

    if ctx.triggered_id == "btn-add-user":
        if not password:
            return "⚠️ Password is required."
        ht.set_password(username, password)
        ht.save()
        return f"✅ User '{username}' added."

    if ctx.triggered_id == "btn-remove-user":
        if username not in ht.users():
            return f"⚠️ User '{username}' not found."
        if len(ht.users()) == 1:
            return "⚠️ Cannot remove the last user — you'd be locked out."
        ht.delete(username)
        ht.save()
        return f"✅ User '{username}' removed."

    return no_update


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=8050)
