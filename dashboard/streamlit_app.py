import sys
from pathlib import Path

import streamlit as st
from streamlit import components

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from .api import api_get, get_base_url, set_base_url
    from .styles import build_custom_css, load_base_css
    from .tabs import tab_countdown, tab_emotion, tab_monitor, tab_water, render_camera_component
except ImportError:
    from dashboard.api import api_get, get_base_url, set_base_url
    from dashboard.styles import build_custom_css, load_base_css
    from dashboard.tabs import tab_countdown, tab_emotion, tab_monitor, tab_water, render_camera_component


def main() -> None:
    st.set_page_config(page_title="SWSC - Study Assistant", layout="centered", page_icon="📚")

    auto_fn = getattr(st, "autorefresh", None)
    if callable(auto_fn):
        auto_fn(interval=1000, key="hidden-autorefresh", limit=None, rerun=True)

    css_text = load_base_css()
    st.markdown(build_custom_css(css_text), unsafe_allow_html=True)
    st.markdown("<h1>📚 SWSC – Study Assistant</h1>", unsafe_allow_html=True)

    base = get_base_url()
    set_base_url(base)

    st.caption(f"🔗 API: {base}")

    st.markdown("---")
    st.subheader("Mode Pengambilan Data")
    if "sim_mode" not in st.session_state:
        st.session_state.sim_mode = False
    if "sim_temp" not in st.session_state:
        st.session_state.sim_temp = 25.0
    if "sim_hum" not in st.session_state:
        st.session_state.sim_hum = 60.0
    if "sim_cloth" not in st.session_state:
        st.session_state.sim_cloth = 1
    if "sim_light" not in st.session_state:
        st.session_state.sim_light = "Terang"

    probe_data, probe_err = api_get("/status")
    mqtt_available = bool(not probe_err and probe_data.get("mqtt_connected", False))

    sim_disabled = False
    if not mqtt_available:
        st.session_state.sim_mode = True
        sim_disabled = True

    st.session_state.sim_mode = st.checkbox(
        "Simulation mode",
        value=st.session_state.sim_mode,
        help="Jalankan dashboard tanpa MQTT dengan data dummy",
        disabled=sim_disabled,
    )

    sim_placeholder = st.empty()
    if st.session_state.sim_mode:
        with sim_placeholder.container():
            temp_col, hum_col, cloth_col, light_col = st.columns([1, 1, 1, 1])
            with temp_col:
                st.session_state.sim_temp = st.number_input("Temp (°C)", value=float(st.session_state.sim_temp), step=0.5, format="%.1f")
            with hum_col:
                st.session_state.sim_hum = st.number_input("Humidity (%)", value=float(st.session_state.sim_hum), step=1.0, format="%.1f")
            with cloth_col:
                st.session_state.sim_cloth = st.selectbox(
                    "Pakaian",
                    options=[0, 1, 2],
                    index=int(st.session_state.sim_cloth),
                    format_func=lambda x: {0: "Tipis", 1: "Sedang", 2: "Tebal"}.get(x, "Sedang"),
                )
            with light_col:
                st.session_state.sim_light = st.selectbox("Light", options=["Gelap", "Redup", "Terang"], index=["Gelap", "Redup", "Terang"].index(st.session_state.sim_light))
    else:
        sim_placeholder.empty()

    def build_status_path(sim: bool) -> str:
        if not sim:
            return "/status"
        return (
            f"/status?simulate=1"
            f"&temperature={st.session_state.sim_temp}"
            f"&humidity={st.session_state.sim_hum}"
            f"&clothing_insulation={st.session_state.sim_cloth}"
            f"&light={0 if st.session_state.sim_light == 'Gelap' else (50 if st.session_state.sim_light == 'Redup' else 150)}"
        )

    if st.session_state.sim_mode:
        status_path = build_status_path(True)
        data, err = api_get(status_path)
    else:
        data, err = probe_data, probe_err
    forced_sim = sim_disabled

    if err:
        st.markdown("""
            <div style="background:#fdeaea; border-left:4px solid #f3b6b6; padding:1rem; border-radius:8px; margin:1rem 0;">
                <strong>⚠️ Connection Error</strong><br>
                Unable to connect to the API. Please ensure the backend is running.
            </div>
        """, unsafe_allow_html=True)
        st.code(str(err))
        return

    if forced_sim:
        st.session_state["forced_sim_warning"] = True
    else:
        st.session_state["forced_sim_warning"] = False

    if st.session_state.get("forced_sim_warning"):
        st.warning("Tidak ada sensor/MQTT terhubung. Beralih ke Simulation mode otomatis.")

    st.markdown("<br>", unsafe_allow_html=True)
    status = data.get("status", "-")
    alert = data.get("alert_level", "-")
    mqtt_ok = "Terhubung" if data.get("mqtt_connected") else "Tidak terhubung"
    clothing = data.get("clothing") or {}
    cloth_label = {0: "Tipis", 1: "Sedang", 2: "Tebal"}.get(int(clothing.get("insulation", 1)), "Sedang")
    sim_label = "Simulasi" if st.session_state.sim_mode else "Realtime"
    alert_map = {"ideal": "Ideal", "kurang_ideal": "Kurang Ideal", "tidak_ideal": "Tidak Ideal"}
    alert_txt = alert_map.get(alert, alert)
    st.caption(f"Status: {status} ({alert_txt}) • MQTT: {mqtt_ok} • Pakaian: {cloth_label} • Mode: {sim_label}")

    tabs = ["Countdown", "Ceklis Air", "Monitoring", "Emotion"]
    params = st.query_params
    if "active_tab" not in st.session_state:
        tab_param = params.get("tab")
        tab_val = None
        if tab_param:
            if isinstance(tab_param, list):
                tab_val = tab_param[0]
            else:
                tab_val = str(tab_param)
        st.session_state.active_tab = tab_val if tab_val in tabs else tabs[0]

    tab_cols = st.columns(len(tabs))
    for i, name in enumerate(tabs):
        with tab_cols[i]:
            if st.button(name, use_container_width=True, type="primary" if st.session_state.active_tab == name else "secondary"):
                st.session_state.active_tab = name
                st.query_params["tab"] = name
                st.rerun()

    sched = data.get("scheduler", {}) or {}
    plan = sched.get("plan") or {}
    water_active = sched.get("water_active") or {}

    if st.session_state.active_tab == "Countdown":
        tab_countdown(plan, sched)
    elif st.session_state.active_tab == "Ceklis Air":
        tab_water(plan, water_active)
    elif st.session_state.active_tab == "Monitoring":
        tab_monitor(data)
    elif st.session_state.active_tab == "Emotion":
        tab_emotion(data)

    st.markdown("---")
    is_running = sched.get("running", False)
    render_camera_component(is_running)


if __name__ == "__main__":
    main()