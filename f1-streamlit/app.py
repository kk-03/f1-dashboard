"""F1 Telemetry dashboard — run with:  streamlit run app.py"""

import streamlit as st

st.set_page_config(page_title="F1 Telemetry", page_icon="🏁", layout="wide")


def coming_soon(title: str, slug: str, blurb: str) -> st.Page:
    """A placeholder tab for a page that isn't built yet."""
    def page():
        st.header(title)
        st.info("🚧 Coming soon")
        st.caption(blurb)

    page.__name__ = f"soon_{slug}"  # each page function needs a unique name
    return st.Page(page, title=f"{title} · soon", icon="⏳", url_path=slug)


# Tabs across the top. When a page is ready, swap its coming_soon(...) line
# for a real one, e.g.  st.Page("views/strategy.py", title="Tyre Strategy", icon="🛞")
pages = [
    st.Page("views/highlights.py", title="Weekend Highlights", icon="🏆", default=True),
    coming_soon("Tyre Strategy", "strategy", "Stints, compounds and pit stops for every driver."),
    coming_soon("Race Pace", "pace", "Lap-by-lap pace and gaps through the race."),
]

st.navigation(pages, position="top").run()
