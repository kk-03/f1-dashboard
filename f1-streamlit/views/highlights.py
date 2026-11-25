"""Weekend Highlights page."""

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from openf1 import (flag_emoji, format_lap, get, is_mobile, load_drivers, session_picker,
                    to_time)

PURPLE = "#a020f0"   # F1 colour for the session-best sector
GREY = "#44445a"
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#f0f0f5"),
)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

meeting, session = session_picker()
session_key = int(session["session_key"])

with st.spinner("Loading session data…"):
    drivers = load_drivers(session_key)
    laps = get("laps", {"session_key": session_key})

if laps.empty or drivers.empty:
    st.info("No lap data available for this session yet.")
    st.stop()

laps = laps[laps["lap_duration"].notna()].copy()
laps["start"] = to_time(laps["date_start"])
laps["is_pit_out_lap"] = laps["is_pit_out_lap"].fillna(False).astype(bool)
laps = laps[laps["driver_number"].isin(drivers.index)]


def acronym(num):
    return drivers.loc[num, "name_acronym"]


def team(num):
    return drivers.loc[num, "team_name"]


def colour(num):
    return drivers.loc[num, "colour"]


def lap_window(lap) -> dict:
    """Date filters covering exactly one lap."""
    start = lap["start"]
    end = start + pd.to_timedelta(lap["lap_duration"], unit="s")
    fmt = "%Y-%m-%dT%H:%M:%S.%f"
    return {"date>=": start.strftime(fmt), "date<=": end.strftime(fmt)}


# Fastest lap per driver (excluding pit-out laps), fastest first
timed = laps[~laps["is_pit_out_lap"] & laps["start"].notna()]
best_laps = timed.sort_values("lap_duration").drop_duplicates("driver_number")
if best_laps.empty:
    st.info("No complete timed laps in this session.")
    st.stop()
fastest = best_laps.iloc[0]

# ---------------------------------------------------------------------------
# Layout: event info (left) | results (right)
# ---------------------------------------------------------------------------

left, right = st.columns([1, 1.6], gap="large")

with left:
    st.caption("WEEKEND HIGHLIGHTS")
    # Race name with the flag right beside it, vertically centred
    flag_url = meeting.get("country_flag")
    # The spacing sits on the flag itself (margin-left), because Streamlit wraps
    # heading contents in its own element, so container gaps don't apply.
    flag_style = "margin-left:0.6em;vertical-align:middle;display:inline-block"
    if isinstance(flag_url, str) and flag_url.startswith("http"):
        flag_html = (f'<img src="{html.escape(flag_url)}" alt="flag" style="{flag_style};'
                     'height:0.9em;border-radius:3px;box-shadow:0 0 0 1px #33334a;'
                     'position:relative;top:-0.08em">')
    else:
        flag_html = f'<span style="{flag_style}">{flag_emoji(meeting.get("country_code"))}</span>'
    st.markdown(
        f'<h2 style="margin:0;padding:0;line-height:1.3">'
        f'{html.escape(str(meeting["meeting_name"]))}{flag_html}</h2>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"{meeting.get('circuit_short_name', '')} · {meeting.get('location', '')} · "
        f"{session['session_name']}"
    )

    # Track map from the fastest lap's car positions
    location = get(
        "location",
        {"session_key": session_key, "driver_number": int(fastest["driver_number"]),
         **lap_window(fastest)},
    )
    if not location.empty:
        location = location[(location["x"] != 0) | (location["y"] != 0)]
        track = go.Figure(go.Scatter(
            x=location["x"], y=location["y"], mode="lines",
            line=dict(color="#f0f0f5", width=5), hoverinfo="skip",
        ))
        track.update_layout(
            **CHART_LAYOUT, height=340, showlegend=False,
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(visible=False),
            yaxis=dict(visible=False, scaleanchor="x", scaleratio=1),
        )
        # Static so it doesn't grab touch-scrolling on phones
        st.plotly_chart(track, config={"staticPlot": True})

    circuit_type = meeting.get("circuit_type")
    if isinstance(circuit_type, str) and circuit_type:
        st.markdown(f"**Circuit type:** {circuit_type}")

with right:
    # --- Podium / top 3 ---------------------------------------------------
    is_race = session.get("session_type") == "Race"
    st.subheader("Podium" if is_race else "Top 3")

    results = get("session_result", {"session_key": session_key})
    if not results.empty and "position" in results:
        top3 = results[results["position"].isin([1, 2, 3])].sort_values("position")
        top3 = list(zip(top3["position"].astype(int), top3["driver_number"]))
    else:
        # Fallback: last recorded position of each driver
        pos = get("position", {"session_key": session_key})
        pos = pos.sort_values("date").drop_duplicates("driver_number", keep="last")
        pos = pos[pos["position"] <= 3].sort_values("position")
        top3 = list(zip(pos["position"].astype(int), pos["driver_number"]))

    # One flex row (not st.columns) so it stays 2nd–1st–3rd side by side on
    # phones instead of stacking into a single column.
    by_pos = dict(top3)
    cards = []
    for p, offset in [(2, 24), (1, 0), (3, 40)]:
        num = by_pos.get(p)
        if num is None or num not in drivers.index:
            cards.append('<div style="flex:1"></div>')
            continue
        d = drivers.loc[num]
        cards.append(
            f'<div style="flex:1;min-width:0;margin-top:{offset}px;'
            f'border-top:4px solid {d["colour"]};background:#1f1f2b;border-radius:8px;'
            f'padding:10px 6px;text-align:center">'
            f'<div style="color:#9a9ab0;font-size:0.8rem">P{p}</div>'
            f'<div style="font-size:clamp(1.2rem,5vw,1.7rem);font-weight:700">'
            f'{html.escape(str(d["name_acronym"]))}</div>'
            f'<div style="font-size:0.8rem;overflow-wrap:anywhere">'
            f'{html.escape(str(d["full_name"]))}</div>'
            f'<div style="color:#9a9ab0;font-size:0.72rem;overflow-wrap:anywhere">'
            f'{html.escape(str(d["team_name"]))}</div></div>'
        )
    st.markdown(
        '<div style="display:flex;gap:8px;align-items:flex-start;margin-bottom:12px">'
        + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )

    # --- Fastest lap with sector bar ----------------------------------------
    st.subheader("Fastest lap")
    fl_num = fastest["driver_number"]
    st.markdown(
        f"**{acronym(fl_num)}** · {team(fl_num)} · "
        f"<span style='font-size:1.3rem;font-weight:700'>{format_lap(fastest['lap_duration'])}</span>"
        f" <span style='color:#9a9ab0'>(lap {int(fastest['lap_number'])})</span>",
        unsafe_allow_html=True,
    )

    sector_cols = ["duration_sector_1", "duration_sector_2", "duration_sector_3"]
    best_sectors = {c: laps[c].min() for c in sector_cols}
    bar = go.Figure()
    for i, c in enumerate(sector_cols, start=1):
        value = fastest[c]
        if pd.isna(value):
            continue
        is_best = np.isclose(value, best_sectors[c])
        bar.add_trace(go.Bar(
            x=[value], y=[""], orientation="h",
            marker=dict(color=PURPLE if is_best else GREY, line=dict(color="#15151e", width=2)),
            text=f"S{i}  {value:.3f}", textposition="inside", insidetextanchor="middle",
            hovertemplate=f"Sector {i}: {value:.3f}s<extra></extra>",
        ))
    bar.update_layout(
        **CHART_LAYOUT, barmode="stack", height=70, showlegend=False,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    st.plotly_chart(bar, config={"staticPlot": True})
    st.caption("Purple = fastest sector of the session")

    # --- Fastest sectors + top speeds ---------------------------------------
    sec_col, speed_col = st.columns(2)

    with sec_col:
        st.subheader("Fastest sectors")
        rows = []
        for i, c in enumerate(sector_cols, start=1):
            if laps[c].notna().any():
                row = laps.loc[laps[c].idxmin()]
                rows.append({"Sector": f"S{i}", "Driver": acronym(row["driver_number"]),
                             "Team": team(row["driver_number"]), "Time": f"{row[c]:.3f}s"})
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        ideal = sum(v for v in best_sectors.values() if pd.notna(v))
        st.caption(f"Ideal lap (best sectors combined): **{format_lap(ideal)}**")

    with speed_col:
        st.subheader("Top speeds")
        top = laps.groupby("driver_number")["st_speed"].max().nlargest(3)
        st.dataframe(
            pd.DataFrame({
                "Driver": [acronym(n) for n in top.index],
                "Team": [team(n) for n in top.index],
                "Speed": [f"{v:.0f} km/h" for v in top.values],
            }),
            hide_index=True,
        )
        st.caption("Measured at the speed trap")

# ---------------------------------------------------------------------------
# Fastest lap comparison (telemetry)
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Fastest lap comparison")

options = best_laps["driver_number"].tolist()
pick_col, axis_col = st.columns([3, 1])
chosen = pick_col.multiselect(
    "Drivers to compare", options, default=options[:2], max_selections=4,
    format_func=lambda n: f"{acronym(n)} – {team(n)}",
)
x_mode = axis_col.radio("X axis", ["Distance", "Time"], horizontal=True)

if not chosen:
    st.info("Pick at least one driver to compare.")
    st.stop()

fig = make_subplots(
    rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
    row_heights=[0.45, 0.2, 0.12, 0.23],
)

LINE_DASHES = ["solid", "dash", "dot", "dashdot"]
CONTRAST_COLOURS = ["#ff8700", "#00d2be", "#f5f5f5", "#ff4fd8"]


def similar(c1: str, c2: str, threshold: float = 90) -> bool:
    """True if two hex colours are hard to tell apart."""
    a = np.array([int(c1.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)])
    b = np.array([int(c2.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)])
    return np.linalg.norm(a - b) < threshold


# 1) Load telemetry and integrate speed → distance for each driver
traces_data = []
for num in chosen:
    lap = best_laps[best_laps["driver_number"] == num].iloc[0]
    car = get("car_data", {"session_key": session_key, "driver_number": int(num),
                           **lap_window(lap)})
    if car.empty:
        st.warning(f"No telemetry for {acronym(num)}.")
        continue

    car = car.sort_values("date").copy()
    car["throttle"] = car["throttle"].clip(0, 100)  # raw data sometimes reads 104
    t = (to_time(car["date"]) - lap["start"]).dt.total_seconds().to_numpy()
    v = car["speed"].to_numpy() / 3.6  # m/s
    distance = np.concatenate([[0], np.cumsum((v[1:] + v[:-1]) / 2 * np.diff(t))])
    traces_data.append((num, lap, car, t, distance))

# 2) Integrated distance drifts a little differently for each car, so scale
#    every lap to the same total length. This keeps corners lined up.
if traces_data:
    lap_length = np.median([dist[-1] for *_, dist in traces_data])
    traces_data = [(n, lap, car, t, dist * lap_length / dist[-1])
                   for n, lap, car, t, dist in traces_data]

# 3) Plot — line style by pick order, swap colours that look too alike
used_colours = []
for i, (num, lap, car, t, distance) in enumerate(traces_data):
    x = distance if x_mode == "Distance" else t
    d = drivers.loc[num]
    col = d["colour"]
    if any(similar(col, c) for c in used_colours):
        col = next(c for c in CONTRAST_COLOURS if not any(similar(c, u) for u in used_colours))
    used_colours.append(col)

    name = f"{d['name_acronym']} {format_lap(lap['lap_duration'])}"
    line = dict(color=col, width=2, dash=LINE_DASHES[i % len(LINE_DASHES)])
    for row, channel in enumerate(["speed", "throttle", "brake", "rpm"], start=1):
        fig.add_trace(
            go.Scatter(
                x=x, y=car[channel], name=name, legendgroup=str(num),
                showlegend=(row == 1), line=line, mode="lines",
                line_shape="hv" if channel == "brake" else "linear",
            ),
            row=row, col=1,
        )

if traces_data and x_mode == "Distance":
    st.caption(f"Lap length from telemetry: {lap_length / 1000:.2f} km")

fig.update_yaxes(title_text="Speed (km/h)", row=1, col=1)
fig.update_yaxes(title_text="Throttle (%)", range=[-5, 105], row=2, col=1)
fig.update_yaxes(title_text="Brake", tickvals=[0, 100], ticktext=["off", "on"], row=3, col=1)
fig.update_yaxes(title_text="RPM", row=4, col=1)
fig.update_xaxes(title_text="Distance (m)" if x_mode == "Distance" else "Time (s)", row=4, col=1)
fig.update_xaxes(gridcolor="#33334a")
# Lock the y axes so dragging only zooms along the lap (easier on touchscreens)
fig.update_yaxes(gridcolor="#33334a", zeroline=False, fixedrange=True)
fig.update_layout(
    **CHART_LAYOUT, height=680 if is_mobile() else 820, hovermode="x unified",
    margin=dict(l=60, r=20, t=10, b=40),
    legend=dict(orientation="h", y=1.04, x=0),
)
st.plotly_chart(fig)
st.caption("Click a name in the legend to hide/show that driver. Drag to zoom, double-click to reset.")
