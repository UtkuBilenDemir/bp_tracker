#!/usr/bin/env python3
"""
Plotly/Dash dashboard for blood pressure readings.
Auto-refreshes when data/readings.csv changes.
Run with: uv run python dashboard.py
"""

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, callback

import config

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Dash(__name__)
server = app.server  # exposed for gunicorn

app.layout = html.Div(
    style={"fontFamily": "system-ui, sans-serif", "maxWidth": "1100px", "margin": "0 auto", "padding": "24px"},
    children=[
        html.H2("Blood Pressure Tracker", style={"marginBottom": "4px"}),
        html.P(
            [
                f"Baseline: {config.BASELINE_SYSTOLIC}/{config.BASELINE_DIASTOLIC} mmHg  ·  HR {config.BASELINE_HR} bpm",
                html.Span(
                    f"  ·  Current dose: {config.CURRENT_DOSE_MG} mg/day",
                    style={"color": "#e67e22", "fontWeight": "500"},
                ),
            ],
            style={"color": "#888", "marginTop": "0"},
        ),
        dcc.Graph(id="bp-chart", config={"displayModeBar": False}),
        dcc.Graph(id="hr-chart", config={"displayModeBar": False}),
        dcc.Interval(id="refresh", interval=15_000, n_intervals=0),  # poll every 15 s
    ],
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    try:
        df = pd.read_csv(config.CSV_PATH, parse_dates=["timestamp"])
    except FileNotFoundError:
        return pd.DataFrame(columns=config.CSV_COLUMNS)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Colour zone helpers
# ---------------------------------------------------------------------------

def bp_zone_shapes(df: pd.DataFrame) -> list[dict]:
    """Horizontal band shapes for normal / elevated / high zones."""
    if df.empty:
        return []

    x0 = df["timestamp"].min()
    x1 = df["timestamp"].max()

    return [
        # Normal — green
        dict(type="rect", xref="x", yref="y",
             x0=x0, x1=x1, y0=0, y1=config.ELEVATED_SYSTOLIC,
             fillcolor="rgba(72,199,142,0.08)", line_width=0, layer="below"),
        # Elevated — yellow
        dict(type="rect", xref="x", yref="y",
             x0=x0, x1=x1, y0=config.ELEVATED_SYSTOLIC, y1=config.HIGH_SYSTOLIC,
             fillcolor="rgba(255,221,87,0.12)", line_width=0, layer="below"),
        # High — red
        dict(type="rect", xref="x", yref="y",
             x0=x0, x1=x1, y0=config.HIGH_SYSTOLIC, y1=220,
             fillcolor="rgba(255,99,71,0.10)", line_width=0, layer="below"),
    ]


def bp_zone_annotations() -> list[dict]:
    return [
        dict(xref="paper", yref="y", x=1.01, y=config.ELEVATED_SYSTOLIC,
             text="Elevated", showarrow=False, font=dict(size=10, color="#b8a100"), xanchor="left"),
        dict(xref="paper", yref="y", x=1.01, y=config.HIGH_SYSTOLIC,
             text="High", showarrow=False, font=dict(size=10, color="#c0392b"), xanchor="left"),
    ]


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("bp-chart", "figure"),
    Output("hr-chart", "figure"),
    Input("refresh", "n_intervals"),
)
def update_charts(_n):
    df = load_data()

    # ── BP chart ──────────────────────────────────────────────────────────
    fig_bp = go.Figure()

    if not df.empty:
        # Colour zones
        fig_bp.update_layout(shapes=bp_zone_shapes(df), annotations=bp_zone_annotations())

        # Baseline reference lines
        for y, label, color in [
            (config.BASELINE_SYSTOLIC, f"Baseline sys {config.BASELINE_SYSTOLIC}", "#2980b9"),
            (config.BASELINE_DIASTOLIC, f"Baseline dia {config.BASELINE_DIASTOLIC}", "#8e44ad"),
        ]:
            fig_bp.add_hline(y=y, line_dash="dot", line_color=color, opacity=0.5,
                             annotation_text=label, annotation_position="bottom right")

        # Hover text
        hover = df.apply(
            lambda r: (
                f"<b>{r['timestamp'].strftime('%d %b %Y  %H:%M')}</b><br>"
                f"BP: {r['systolic']}/{r['diastolic']} mmHg<br>"
                f"HR: {r['heart_rate']} bpm<br>"
                + (f"Dose: {config.CURRENT_DOSE_MG} mg  ·  taken {r['dose_time']}<br>" if r.get("dose_taken") else "No dose<br>")
                + f"<i>{r.get('ai_comment', '')}</i>"
            ),
            axis=1,
        )

        marker_symbol = df["dose_taken"].map(lambda d: "diamond" if d else "circle")

        fig_bp.add_trace(go.Scatter(
            x=df["timestamp"], y=df["systolic"],
            mode="lines+markers",
            name="Systolic",
            line=dict(color="#e74c3c", width=2),
            marker=dict(size=9, symbol=marker_symbol),
            hovertext=hover, hoverinfo="text",
        ))
        fig_bp.add_trace(go.Scatter(
            x=df["timestamp"], y=df["diastolic"],
            mode="lines+markers",
            name="Diastolic",
            line=dict(color="#8e44ad", width=2),
            marker=dict(size=9, symbol=marker_symbol),
            hovertext=hover, hoverinfo="text",
        ))

    fig_bp.update_layout(
        title="Blood Pressure over Time",
        yaxis_title="mmHg",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(r=80),
        height=380,
    )
    fig_bp.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
    fig_bp.update_yaxes(showgrid=True, gridcolor="#f0f0f0", range=[40, 200])

    # ── HR chart ──────────────────────────────────────────────────────────
    fig_hr = go.Figure()

    if not df.empty:
        fig_hr.add_hline(
            y=config.BASELINE_HR, line_dash="dot", line_color="#27ae60", opacity=0.5,
            annotation_text=f"Baseline HR {config.BASELINE_HR}", annotation_position="bottom right",
        )
        fig_hr.add_trace(go.Scatter(
            x=df["timestamp"], y=df["heart_rate"],
            mode="lines+markers",
            name="Heart rate",
            line=dict(color="#27ae60", width=2),
            marker=dict(size=9, symbol=df["dose_taken"].map(lambda d: "diamond" if d else "circle")),
            hovertemplate="%{x|%d %b %H:%M}<br>HR: %{y} bpm<extra></extra>",
        ))

    fig_hr.update_layout(
        title="Heart Rate over Time",
        yaxis_title="bpm",
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(r=80),
        height=260,
    )
    fig_hr.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
    fig_hr.update_yaxes(showgrid=True, gridcolor="#f0f0f0", range=[40, 140])

    return fig_bp, fig_hr


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=8050)
