import sys
from pathlib import Path

import streamlit as st

# Ensure project root on sys.path so absolute imports work when run via `streamlit run`
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Support running via Streamlit script (no package parent) or as module
try:
    from .api import api_get, get_base_url, set_base_url
    from .styles import build_custom_css, load_base_css
    from .tabs import navbar, tab_countdown, tab_emotion, tab_monitor, tab_water
    from .utils import trigger_autorefresh
except ImportError:  # pragma: no cover - fallback for direct script run
    from dashboard.api import api_get, get_base_url, set_base_url
    from dashboard.styles import build_custom_css, load_base_css
    from dashboard.tabs import navbar, tab_countdown, tab_emotion, tab_monitor, tab_water
    from dashboard.utils import trigger_autorefresh


def main() -> None:
    st.set_page_config(page_title="SWSC - Study Assistant", layout="centered", page_icon="📚")

    css_text = load_base_css()
    st.markdown(build_custom_css(css_text), unsafe_allow_html=True)
    st.markdown("<h1>📚 SWSC – Study Assistant</h1>", unsafe_allow_html=True)

    base = get_base_url()
    set_base_url(base)

    col_api, col_auto, col_refresh = st.columns([3, 1, 1])
    with col_api:
        st.caption(f"🔗 API: {base}")
    with col_auto:
        auto = st.checkbox("Auto refresh", value=True, help="Refresh every 5 seconds")
        trigger_autorefresh(auto)
    with col_refresh:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄", use_container_width=True, help="Refresh now"):
            st.rerun()

    data, err = api_get("/status")
    if err:
        st.markdown("""
            <div style="background:#fdeaea; border-left:4px solid #f3b6b6; padding:1rem; border-radius:8px; margin:1rem 0;">
                <strong>⚠️ Connection Error</strong><br>
                Unable to connect to the API. Please ensure the backend is running.
            </div>
        """, unsafe_allow_html=True)
        st.code(str(err))
        return

    st.markdown("<br>", unsafe_allow_html=True)
    navbar(data.get("sensor", {}), data.get("status", "-"), data.get("alert_level", "-"))

    tabs = st.tabs(["Countdown", "Ceklis Air", "Monitoring", "Emotion"])
    sched = data.get("scheduler", {}) or {}
    plan = sched.get("plan") or {}
    water_active = sched.get("water_active") or {}

    with tabs[0]:
        tab_countdown(plan, sched)
    with tabs[1]:
        tab_water(plan, water_active)
    with tabs[2]:
        tab_monitor(data)
    with tabs[3]:
        tab_emotion(data)


if __name__ == "__main__":
    main()
