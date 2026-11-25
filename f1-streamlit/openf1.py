"""Shared helpers: OpenF1 requests (cached), session picker, driver styling."""

import time
from datetime import datetime, timezone
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

API = "https://api.openf1.org/v1"
FIRST_YEAR = 2023  # OpenF1 historical data starts in 2023

_last_request = 0.0


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

def _build_url(endpoint: str, params: dict) -> str:
    """Build an OpenF1 URL. Keys may end in an operator, e.g. {"date>=": "..."}."""
    parts = []
    for key, value in params.items():
        value = quote(str(value), safe="")
        if key.endswith((">", "<", ">=", "<=")):
            parts.append(f"{key}{value}")      # date>=2026-...
        else:
            parts.append(f"{key}={value}")     # session_key=11420
    return f"{API}/{endpoint}?" + "&".join(parts)


@st.cache_data(ttl=3600, show_spinner=False)
def get(endpoint: str, params: dict) -> pd.DataFrame:
    """Fetch an OpenF1 endpoint as a DataFrame. Results are cached for an hour."""
    global _last_request
    url = _build_url(endpoint, params)

    for attempt in range(4):
        # Free tier allows 3 requests/second — keep a small gap between calls
        wait = 0.4 - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()

        res = requests.get(url, timeout=30)
        if res.status_code == 429:          # rate limited: back off and retry
            time.sleep(3 * (attempt + 1))
            continue
        if res.status_code == 404:          # OpenF1 returns 404 for "no results"
            return pd.DataFrame()
        res.raise_for_status()
        return pd.DataFrame(res.json())

    raise RuntimeError("OpenF1 rate limit reached — wait a minute and refresh.")


def to_time(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="ISO8601")


# ---------------------------------------------------------------------------
# Sidebar session picker (shared by every page)
# ---------------------------------------------------------------------------

def is_mobile() -> bool:
    """Best guess at whether the visitor is on a phone, from the browser's user agent."""
    try:
        agent = st.context.headers.get("User-Agent", "")
    except Exception:
        return False
    return any(word in agent for word in ("iPhone", "Android", "Mobile"))


def session_picker():
    """Pickers for year → race → session. Returns (meeting, session) rows.

    On desktop they live in the sidebar. On phones the sidebar is hidden behind
    a small arrow, so they go in a collapsible box at the top of the page instead.
    """
    now = datetime.now(timezone.utc)
    if is_mobile():
        ui = st.expander("🏁 Choose year / race / session")
    else:
        ui = st.sidebar
        ui.header("Session")

    years = list(range(now.year, FIRST_YEAR - 1, -1))
    year = ui.selectbox("Year", years, key="year")

    meetings = get("meetings", {"year": year})
    if meetings.empty:
        ui.warning("No races found for this year.")
        st.stop()
    meetings["start"] = to_time(meetings["date_start"])
    meetings = meetings[meetings["start"] < now].sort_values("start", ascending=False)
    if meetings.empty:
        ui.warning("No races have started yet this year.")
        st.stop()

    meeting_name = ui.selectbox("Race", meetings["meeting_name"].tolist(), key="meeting")
    meeting = meetings[meetings["meeting_name"] == meeting_name].iloc[0]

    sessions = get("sessions", {"meeting_key": int(meeting["meeting_key"])})
    sessions = sessions[sessions["date_end"].notna()].copy()
    sessions["end"] = to_time(sessions["date_end"])
    sessions = sessions[sessions["end"] < now].sort_values("end")
    if sessions.empty:
        ui.warning("No completed sessions for this event yet.")
        st.stop()

    names = sessions["session_name"].tolist()
    default = names.index("Race") if "Race" in names else len(names) - 1
    session_name = ui.selectbox("Session", names, index=default)
    session = sessions[sessions["session_name"] == session_name].iloc[0]

    ui.caption("Data: [OpenF1](https://openf1.org) · free historical tier")
    return meeting, session


# ---------------------------------------------------------------------------
# Drivers, team colours and teammate line styles
# ---------------------------------------------------------------------------

# Teammates share a colour, so the second driver (by car number) gets a
# dashed line and different marker.
TEAMMATE_STYLES = [
    {"dash": "solid", "symbol": "circle"},
    {"dash": "dash", "symbol": "diamond"},
    {"dash": "dot", "symbol": "square"},
]


def load_drivers(session_key: int) -> pd.DataFrame:
    drivers = get("drivers", {"session_key": session_key})
    if drivers.empty:
        return drivers
    drivers = drivers.drop_duplicates("driver_number").copy()
    drivers["colour"] = "#" + drivers["team_colour"].fillna("888888").astype(str)
    drivers["team_name"] = drivers["team_name"].fillna("Unknown")
    drivers = drivers.sort_values(["team_name", "driver_number"])
    drivers["team_index"] = drivers.groupby("team_name").cumcount()
    drivers["dash"] = drivers["team_index"].map(lambda i: TEAMMATE_STYLES[i % 3]["dash"])
    drivers["symbol"] = drivers["team_index"].map(lambda i: TEAMMATE_STYLES[i % 3]["symbol"])
    return drivers.set_index("driver_number", drop=False)


def format_lap(seconds) -> str:
    if seconds is None or pd.isna(seconds):
        return "–"
    minutes, secs = divmod(float(seconds), 60)
    return f"{int(minutes)}:{secs:06.3f}" if minutes else f"{secs:.3f}s"


# ---------------------------------------------------------------------------
# Country flags
# ---------------------------------------------------------------------------

_ALPHA2 = {
    "AUS": "AU", "CHN": "CN", "JPN": "JP", "BRN": "BH", "BHR": "BH", "KSA": "SA",
    "SAU": "SA", "USA": "US", "ITA": "IT", "MON": "MC", "MCO": "MC", "ESP": "ES",
    "CAN": "CA", "AUT": "AT", "GBR": "GB", "BEL": "BE", "HUN": "HU", "NED": "NL",
    "NLD": "NL", "AZE": "AZ", "SGP": "SG", "MEX": "MX", "BRA": "BR", "QAT": "QA",
    "UAE": "AE", "ARE": "AE", "POR": "PT", "PRT": "PT", "GER": "DE", "DEU": "DE",
    "FRA": "FR", "RUS": "RU", "TUR": "TR",
}


def flag_emoji(country_code) -> str:
    alpha2 = _ALPHA2.get(str(country_code).upper())
    if not alpha2:
        return "🏁"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in alpha2)
