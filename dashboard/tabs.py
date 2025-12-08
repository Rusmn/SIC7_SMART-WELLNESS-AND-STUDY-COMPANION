from typing import Any, Dict

import streamlit as st
from streamlit import components

# Support running as package or direct script import
try:
    from .api import api_get, api_get_plan, api_post, get_base_url
    from .utils import fmt_sec
except ImportError:  # pragma: no cover - fallback for direct script run
    from dashboard.api import api_get, api_get_plan, api_post, get_base_url
    from dashboard.utils import fmt_sec


def navbar(metrics: Dict[str, Any], status: str, alert: str) -> None:
    """Display sensor metrics in clean card layout."""
    light_txt = "Gelap" if str(metrics.get("light", "0")) == "0.0" or str(metrics.get("light", "0")) == "0" else "Terang"
    status_class = "status-good" if alert == "good" else "status-bad"

    col1, col2, col3, col4 = st.columns(4)

    col1.markdown(f"""
        <div class='metric-card'>
            <div class='metric-title'>Temperature</div>
            <div class='metric-value'>{metrics.get('temperature', '-')} °C</div>
        </div>
    """, unsafe_allow_html=True)

    col2.markdown(f"""
        <div class='metric-card'>
            <div class='metric-title'>Humidity</div>
            <div class='metric-value'>{metrics.get('humidity', '-')} %</div>
        </div>
    """, unsafe_allow_html=True)

    col3.markdown(f"""
        <div class='metric-card'>
            <div class='metric-title'>Light</div>
            <div class='metric-value'>{light_txt}</div>
        </div>
    """, unsafe_allow_html=True)

    col4.markdown(f"""
        <div class='metric-card'>
            <div class='metric-title'>Status</div>
            <div class='status-badge {status_class}'>{status}</div>
        </div>
    """, unsafe_allow_html=True)


def tab_countdown(plan: Dict[str, Any], sched: Dict[str, Any]) -> None:
    """Countdown tab with planner and timer display."""
    st.markdown("<h2>⏱️ Study Planner</h2>", unsafe_allow_html=True)

    st.markdown('<label style="font-size:0.875rem; font-weight:600; color:var(--text-soft); margin-bottom:0.5rem;">Total Study Duration (minutes)</label>', unsafe_allow_html=True)

    input_col, calc_btn_col = st.columns([4, 1])
    with input_col:
        dur = st.number_input(
            "Total Study Duration (minutes)",
            min_value=1,
            max_value=360,
            value=60,
            step=5,
            key="dur_input",
            label_visibility="collapsed"
        )
    with calc_btn_col:
        if st.button("Calculate", use_container_width=True, type="primary"):
            new_plan, err = api_get_plan(int(dur))
            if err:
                st.error(str(err))
            else:
                st.session_state["plan_cache"] = new_plan

    show_plan = st.session_state.get("plan_cache") or plan
    if show_plan and show_plan.get('break_interval_min'):
        water_milestones = show_plan.get('water_milestones', [])
        plan_html = f"""
        <div class="plan-summary-grid">
            <div class="plan-item">
                <div class="plan-label">Break Interval</div>
                <div class="plan-value">{show_plan.get('break_interval_min', '-')} min</div>
            </div>
            <div class="plan-item">
                <div class="plan-label">Total Breaks</div>
                <div class="plan-value">{show_plan.get('break_count', '-')}</div>
            </div>
            <div class="plan-item">
                <div class="plan-label">Break Length</div>
                <div class="plan-value">{show_plan.get('break_length_min', '-')} min</div>
            </div>
            <div class="plan-item">
                <div class="plan-label">Water Milestones</div>
                <div class="plan-value">{len(water_milestones)}</div>
            </div>
            <div class="plan-item">
                <div class="plan-label">Per Milestone</div>
                <div class="plan-value">{show_plan.get('water_amount_ml_per', show_plan.get('water_ml', '-'))} ml</div>
            </div>
            <div class="plan-item">
                <div class="plan-label">Total Water</div>
                <div class="plan-value">{show_plan.get('water_total_ml', '-')} ml</div>
            </div>
        </div>
        """
        st.markdown(plan_html, unsafe_allow_html=True)
    else:
        st.markdown("""
            <div class="info-box">
                💡 Enter your study duration above and click <strong>Calculate</strong> to generate your personalized study plan.
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<h2>🎯 Session Control</h2>", unsafe_allow_html=True)
    btn_col1, btn_col2, btn_col3 = st.columns(3)

    with btn_col1:
        if st.button("▶️ Start", use_container_width=True):
            err = api_post("/start", {"duration_min": int(dur)})
            if err:
                st.error(str(err))
            else:
                new_plan, _ = api_get_plan(int(dur))
                if new_plan:
                    st.session_state["plan_cache"] = new_plan

    with btn_col2:
        if st.button("⏹️ Stop", use_container_width=True):
            err = api_post("/stop", {})
            if err:
                st.error(str(err))

    with btn_col3:
        if st.button("🔄 Reset", use_container_width=True):
            err = api_post("/reset", {})
            if err:
                st.error(str(err))
            else:
                if "plan_cache" in st.session_state:
                    del st.session_state["plan_cache"]

    st.markdown("<h2>⏰ Countdown Timer</h2>", unsafe_allow_html=True)
    phase_name = sched.get("phase", "IDLE").upper()
    phase_sec = sched.get("phase_remaining_sec", 0)
    total_sec = sched.get("total_remaining_sec", 0)

    display_html = f"""
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: "Inter", "Segoe UI", Roboto, Arial, sans-serif;
        }}
        .countdown-display {{
            background: linear-gradient(135deg, #e8f0f7 0%, #f0f4f8 100%);
            border-radius: 14px;
            padding: 2rem;
            text-align: center;
            border: 1px solid rgba(0, 0, 0, 0.08);
            box-shadow: inset 0 1px 1px rgba(255,255,255,0.5), 0 2px 8px rgba(0,0,0,0.06);
            margin: 0;
        }}
        .phase-label {{
            font-weight: 700;
            color: #6a7380;
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 0.5rem;
        }}
        .phase-time {{
            font-size: 3.5rem;
            font-weight: 800;
            color: #1e4b8a;
            margin: 0.75rem 0;
            font-family: 'Courier New', monospace;
            line-height: 1;
        }}
        .sub-time {{
            font-size: 0.875rem;
            color: #6a7380;
            margin-top: 0.5rem;
        }}
    </style>
    <div class="countdown-display">
        <div class="phase-label">{phase_name}</div>
        <div class="phase-time" id="phase-timer">00:00</div>
        <div class="sub-time">
            <strong>Total Remaining:</strong> <span id="total-timer">00:00</span>
        </div>
    </div>
    <script>
        (function() {{
            let phaseRemaining = {phase_sec};
            let totalRemaining = {total_sec};
            const phaseEl = document.getElementById('phase-timer');
            const totalEl = document.getElementById('total-timer');

            function formatTime(seconds) {{
                if (seconds < 0) seconds = 0;
                const m = Math.floor(seconds / 60);
                const s = seconds % 60;
                return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
            }}

            function updateDisplay() {{
                if (phaseEl) phaseEl.textContent = formatTime(phaseRemaining);
                if (totalEl) totalEl.textContent = formatTime(totalRemaining);
            }}

            function countdown() {{
                if (phaseRemaining > 0) phaseRemaining--;
                if (totalRemaining > 0) totalRemaining--;
                updateDisplay();
            }}

            updateDisplay();
            setInterval(countdown, 1000);
        }})();
    </script>
    """
    components.v1.html(display_html, height=220)


def tab_water(plan: Dict[str, Any], water_active: Dict[str, Any]) -> None:
    """Water checklist tab with clean milestone cards."""
    st.markdown("<h2>💧 Water Milestones</h2>", unsafe_allow_html=True)

    milestones = plan.get("water_milestones") or []
    per_ml = plan.get("water_amount_ml_per", plan.get("water_ml", 250))

    if not milestones:
        st.markdown("""
            <div class="info-box">
                💡 Calculate a study plan and start your session to see water milestones here.
                Stay hydrated while studying!
            </div>
        """, unsafe_allow_html=True)
        return

    for idx, tsec in enumerate(milestones):
        time_str = fmt_sec(tsec)
        active = bool(water_active.get(str(idx)))
        active_class = "active" if active else ""
        active_badge = '<span style="color:var(--accent-light);">⏰ ACTIVE</span>' if active else ''

        water_html = f"""<div class="water-milestone {active_class}">
    <div>
        <div style="font-weight:600; font-size:1rem; margin-bottom:0.25rem;">
            💧 Milestone {idx + 1} {active_badge}
        </div>
        <div style="font-size:0.875rem; color:var(--text-soft);">
            At {time_str}
        </div>
    </div>
    <div style="text-align:right;">
        <div style="font-size:1.25rem; font-weight:700; color:var(--accent);">
            {per_ml} ml
        </div>
    </div>
</div>"""

        st.markdown(water_html, unsafe_allow_html=True)

        checked = st.checkbox(
            "✓ Done",
            key=f"water-{idx}",
            value=False,
            help="Check when you've completed this water milestone",
        )

        if checked:
            api_post("/water_ack", {"milestone_id": idx})

    total_water = len(milestones) * per_ml
    st.markdown(f"""
        <div style="margin-top:1.5rem; text-align:center; padding:1rem; background:white; border-radius:10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
            <div style="font-size:0.875rem; color:var(--text-soft); margin-bottom:0.5rem;">Total Water Goal</div>
            <div style="font-size:1.5rem; font-weight:700; color:var(--accent);">{total_water} ml</div>
            <div style="font-size:0.75rem; color:var(--text-soft); margin-top:0.25rem;">{len(milestones)} milestones × {per_ml} ml each</div>
        </div>
    """, unsafe_allow_html=True)


def tab_emotion(data: Dict[str, Any]) -> None:
    """Emotion detection tab with real-time webcam."""
    st.markdown("<h2>😊 Emotion Detection</h2>", unsafe_allow_html=True)

    emotion_data = data.get("emotion", {})
    emotion_label = emotion_data.get("label", "Menunggu...")
    emotion_score = emotion_data.get("score", 0.0)
    emotion_timestamp = emotion_data.get("timestamp", 0)

    sched = data.get("scheduler", {})
    is_running = sched.get("running", False)

    emotion_config = {
        "angry": {"emoji": "😠", "color": "#dc3545", "bg": "#f8d7da", "text": "Marah"},
        "disgust": {"emoji": "🤢", "color": "#6c757d", "bg": "#e2e3e5", "text": "Jijik"},
        "fear": {"emoji": "😨", "color": "#fd7e14", "bg": "#ffe5d0", "text": "Takut"},
        "happy": {"emoji": "😊", "color": "#28a745", "bg": "#d4edda", "text": "Bahagia"},
        "sad": {"emoji": "😢", "color": "#17a2b8", "bg": "#d1ecf1", "text": "Sedih"},
        "surprise": {"emoji": "😲", "color": "#ffc107", "bg": "#fff3cd", "text": "Terkejut"},
        "neutral": {"emoji": "😐", "color": "#6c757d", "bg": "#e2e3e5", "text": "Netral"},
    }

    emotion_key = emotion_label.lower() if isinstance(emotion_label, str) else "neutral"
    config = emotion_config.get(emotion_key, emotion_config["neutral"])

    if emotion_label == "Menunggu...":
        st.markdown("""
            <div class="info-box">
                📸 Real-time emotion detection from webcam.
                The camera will automatically start when you begin a study session.
            </div>
        """, unsafe_allow_html=True)
    else:
        import datetime
        timestamp_str = datetime.datetime.fromtimestamp(emotion_timestamp).strftime("%H:%M:%S") if emotion_timestamp > 0 else "-"

        emotion_display = f"""
        <div style="background:{config['bg']}; border-radius:14px; padding:2rem; text-align:center; border:2px solid {config['color']}; margin:1.5rem 0; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
            <div style="font-size:4rem; margin-bottom:0.5rem;">{config['emoji']}</div>
            <div style="font-size:1.75rem; font-weight:700; color:{config['color']}; margin-bottom:0.5rem;">
                {config['text']}
            </div>
            <div style="font-size:1rem; color:#6a7380; margin-bottom:0.25rem;">
                Confidence: <strong>{emotion_score*100:.1f}%</strong>
            </div>
            <div style="font-size:0.75rem; color:#999;">
                Last updated: {timestamp_str}
            </div>
        </div>
        """
        st.markdown(emotion_display, unsafe_allow_html=True)

    st.markdown("<h3>📷 Live Camera Feed</h3>", unsafe_allow_html=True)

    if "camera_active" not in st.session_state:
        st.session_state.camera_active = False
    if "camera_manual_override" not in st.session_state:
        st.session_state.camera_manual_override = False

    if is_running and not st.session_state.camera_active:
        st.session_state.camera_active = True
        st.session_state.camera_manual_override = False
    elif not is_running and st.session_state.camera_active and not st.session_state.camera_manual_override:
        st.session_state.camera_active = False

    col1, col2 = st.columns([3, 1])
    with col1:
        camera_status = "🟢 Active" if st.session_state.camera_active else "🔴 Inactive"
        session_status = " (Auto - Session Running)" if is_running else " (Manual)" if st.session_state.camera_active else ""
        st.markdown(f"**Camera Status:** {camera_status}{session_status}")
    with col2:
        if st.button("📷 Toggle Camera", use_container_width=True):
            st.session_state.camera_active = not st.session_state.camera_active
            st.session_state.camera_manual_override = st.session_state.camera_active and not is_running
            st.rerun()

    if st.session_state.camera_active or is_running:
        webcam_html = f"""
        <style>
            #webcam-container {{
                background: white;
                border-radius: 10px;
                padding: 1rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                text-align: center;
            }}
            #webcam {{
                width: 100%;
                max-width: 640px;
                border-radius: 8px;
                background: #000;
            }}
            #capture-canvas {{
                display: none;
            }}
        </style>
        <div id="webcam-container">
            <video id="webcam" autoplay playsinline></video>
            <canvas id="capture-canvas"></canvas>
            <div id="status" style="margin-top:0.5rem; font-size:0.875rem; color:#6a7380;">
                Initializing camera...
            </div>
        </div>
        <script>
            if (window.emotionCaptureActive) {{
                console.log('Emotion capture already active, skipping duplicate');
            }} else {{
                window.emotionCaptureActive = true;

                const video = document.getElementById('webcam');
                const canvas = document.getElementById('capture-canvas');
                const status = document.getElementById('status');
                const ctx = canvas.getContext('2d');
                let captureInterval = null;
                let lastCaptureTime = 0;

                navigator.mediaDevices.getUserMedia({{ video: true }})
                    .then(stream => {{
                        video.srcObject = stream;
                        status.textContent = '✅ Camera active - Capturing every 10 seconds';

                        video.onloadedmetadata = () => {{
                            setTimeout(() => {{
                                captureAndSend();
                            }}, 2000);
                        }};

                        captureInterval = setInterval(() => {{
                            captureAndSend();
                        }}, 10000);
                    }})
                    .catch(err => {{
                        status.textContent = '❌ Camera access denied: ' + err.message;
                        window.emotionCaptureActive = false;
                    }});

                function captureAndSend() {{
                    const now = Date.now();
                    if (now - lastCaptureTime < 5000) {{
                        console.log('Skipping capture - too soon since last one');
                        return;
                    }}
                    lastCaptureTime = now;
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;

                ctx.drawImage(video, 0, 0);

                canvas.toBlob(blob => {{
                    const formData = new FormData();
                    formData.append('file', blob, 'webcam.jpg');

                    status.textContent = '📤 Analyzing emotion...';

                    fetch('{get_base_url()}/camera/analyze', {{
                        method: 'POST',
                        body: formData
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        if (data.emotion) {{
                            status.textContent = '✅ Emotion detected: ' + data.emotion.label + ' (' + (data.emotion.score * 100).toFixed(1) + '%)';
                        }} else {{
                            status.textContent = '⚠️ No face detected';
                        }}
                    }})
                    .catch(err => {{
                        status.textContent = '❌ Error: ' + err.message;
                    }});
                }}, 'image/jpeg', 0.9);
            }}

                window.addEventListener('beforeunload', () => {{
                    if (captureInterval) clearInterval(captureInterval);
                    if (video.srcObject) {{
                        video.srcObject.getTracks().forEach(track => track.stop());
                    }}
                    window.emotionCaptureActive = false;
                }});
            }}
        </script>
        """
        components.v1.html(webcam_html, height=500)
    else:
        st.markdown("""
            <div style="background:#f8f9fa; border-radius:10px; padding:2rem; text-align:center; color:#6c757d;">
                📷 Camera is currently inactive<br>
                <small>Start a study session or click "Toggle Camera" to enable</small>
            </div>
        """, unsafe_allow_html=True)

    summary_data, summary_err = api_get("/emotion/summary")

    if summary_err and "404" in str(summary_err):
        st.markdown("""
            <div style="background:#fff3cd; border-left:4px solid #ffc107; padding:1rem; border-radius:8px; margin:1rem 0;">
                <strong>⚠️ Summary Endpoint Not Available</strong><br>
                Please restart the backend server to enable emotion summary and export features.
            </div>
        """, unsafe_allow_html=True)
    elif not summary_err and summary_data and summary_data.get("total_records", 0) > 0:
        st.markdown("<h3>📊 Session Summary</h3>", unsafe_allow_html=True)

        total_records = summary_data["total_records"]
        most_freq = summary_data["most_frequent"]
        emotion_counts = summary_data["emotion_counts"]
        emotion_pcts = summary_data["emotion_percentages"]
        avg_conf = summary_data["average_confidence"]

        emotion_config = {
            "angry": {"emoji": "😠", "color": "#dc3545", "text": "Marah"},
            "disgust": {"emoji": "🤢", "color": "#6c757d", "text": "Jijik"},
            "fear": {"emoji": "😨", "color": "#fd7e14", "text": "Takut"},
            "happy": {"emoji": "😊", "color": "#28a745", "text": "Bahagia"},
            "sad": {"emoji": "😢", "color": "#17a2b8", "text": "Sedih"},
            "surprise": {"emoji": "😲", "color": "#ffc107", "text": "Terkejut"},
            "neutral": {"emoji": "😐", "color": "#6c757d", "text": "Netral"},
        }

        if most_freq and most_freq["label"]:
            mf_label = most_freq["label"]
            mf_config = emotion_config.get(mf_label, {"emoji": "😐", "color": "#6c757d", "text": mf_label})

            summary_html = f"""
            <div style="background:#f8f9fa; border-radius:12px; padding:1.5rem; margin:1rem 0; border:2px solid {mf_config['color']};">
                <div style="text-align:center;">
                    <div style="font-size:3rem;">{mf_config['emoji']}</div>
                    <div style="font-size:1.25rem; font-weight:700; color:{mf_config['color']}; margin:0.5rem 0;">
                        Emosi Paling Sering: {mf_config['text']}
                    </div>
                    <div style="font-size:0.875rem; color:#6a7380;">
                        {most_freq['count']} dari {total_records} deteksi ({most_freq['percentage']:.1f}%)
                    </div>
                    <div style="font-size:0.875rem; color:#6a7380; margin-top:0.5rem;">
                        Rata-rata confidence: <strong>{avg_conf*100:.1f}%</strong>
                    </div>
                </div>
            </div>
            """
            st.markdown(summary_html, unsafe_allow_html=True)

            st.markdown("**Breakdown Emosi:**")
            for emotion_label, count in sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True):
                pct = emotion_pcts.get(emotion_label, 0)
                em_conf = emotion_config.get(emotion_label, {"emoji": "😐", "text": emotion_label})
                st.markdown(f"{em_conf['emoji']} **{em_conf['text']}**: {count} kali ({pct:.1f}%)")

            st.markdown("---")
            col_export1, col_export2 = st.columns([3, 1])
            with col_export1:
                st.markdown("**💾 Export Data**")
                st.caption(f"Total {total_records} emotion records available for export")
            with col_export2:
                export_url = f"{get_base_url()}/emotion/export"
                st.markdown(f'<a href="{export_url}" target="_blank"><button style="background:#28a745; color:white; border:none; padding:8px 16px; border-radius:6px; cursor:pointer; font-weight:600; width:100%;">📥 Download CSV</button></a>', unsafe_allow_html=True)

    st.markdown("<h3>ℹ️ About Real-time Detection</h3>", unsafe_allow_html=True)
    st.markdown("""
        <div style="background:white; border-radius:10px; padding:1rem; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
            <p style="margin:0; font-size:0.875rem; color:#6a7380;">
                📸 The camera automatically starts when you begin a study session and captures your facial expression <strong>every 10 seconds</strong>.
            </p>
            <p style="margin:0.5rem 0 0 0; font-size:0.875rem; color:#6a7380;">
                🤖 The AI analyzes 7 emotions: <strong>Happy, Sad, Angry, Surprise, Fear, Disgust, and Neutral</strong>.
            </p>
            <p style="margin:0.5rem 0 0 0; font-size:0.875rem; color:#6a7380;">
                💡 <em>Tip:</em> Ensure good lighting and sit facing the camera for best results.
            </p>
        </div>
    """, unsafe_allow_html=True)


def tab_monitor(data: Dict[str, Any]) -> None:
    """Environmental monitoring tab with sensor cards."""
    st.markdown("<h2>🌡️ Environment Monitoring</h2>", unsafe_allow_html=True)

    env = data.get("env_prediction", {}) or {}
    sensor = data.get("sensor", {}) or {}
    status_text = data.get("status", "-")
    alert_level = data.get("alert_level", "unknown")
    light_txt = "Gelap" if str(sensor.get("light", "0")) == "0" or str(sensor.get("light", "0")) == "0.0" else "Terang"

    monitor_html = f"""
    <div class="monitor-grid" style="display:grid; grid-template-columns: repeat(3, 1fr); gap:0.75rem; margin:1rem 0;">
        <div class="monitor-card" style="background:white; border-radius:10px; padding:1rem; text-align:center; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border: 1px solid #e2e7f1;">
            <div class="monitor-title" style="font-size:0.875rem; color:var(--text-soft); margin-bottom:0.5rem;">Temperature</div>
            <div class="monitor-value" style="font-size:1.75rem; font-weight:700; color:var(--accent);">{sensor.get('temperature', '-')} °C</div>
        </div>
        <div class="monitor-card" style="background:white; border-radius:10px; padding:1rem; text-align:center; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border: 1px solid #e2e7f1;">
            <div class="monitor-title" style="font-size:0.875rem; color:var(--text-soft); margin-bottom:0.5rem;">Humidity</div>
            <div class="monitor-value" style="font-size:1.75rem; font-weight:700; color:var(--accent);">{sensor.get('humidity', '-')} %</div>
        </div>
        <div class="monitor-card" style="background:white; border-radius:10px; padding:1rem; text-align:center; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border: 1px solid #e2e7f1;">
            <div class="monitor-title" style="font-size:0.875rem; color:var(--text-soft); margin-bottom:0.5rem;">Light</div>
            <div class="monitor-value" style="font-size:1.75rem; font-weight:700; color:var(--accent);">{light_txt}</div>
        </div>
    </div>
    """
    st.markdown(monitor_html, unsafe_allow_html=True)

    if alert_level == "good":
        summary_class = "good"
        summary_text = "Ideal"
        summary_color = "#2b612b"
        summary_bg = "#e6f7e6"
        summary_border = "#a0d9a0"
    elif alert_level == "bad":
        summary_class = "bad"
        summary_text = "Tidak Ideal"
        summary_color = "#8c2e2e"
        summary_bg = "#fdeaea"
        summary_border = "#f3b6b6"
    else:
        summary_class = "unknown"
        summary_text = "Data Tidak Tersedia"
        summary_color = "#6a7380"
        summary_bg = "#f4f4f4"
        summary_border = "#ddd"

    env_label = env.get('label', summary_text)

    summary_html = f"""
    <div class="monitor-summary-card {summary_class}" style="background:{summary_bg}; border-radius:10px; padding:1.5rem; text-align:center; box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin:1.5rem 0; border: 2px solid {summary_border};">
        <div class="monitor-title" style="font-size:0.875rem; color:{summary_color}; margin-bottom:0.5rem; font-weight:600;">
            Environmental Condition
        </div>
        <div class="monitor-value" style="font-size:2rem; font-weight:700; color:{summary_color};">
            {env_label}
        </div>
    </div>
    """
    st.markdown(summary_html, unsafe_allow_html=True)

    st.markdown("""
        <div style="text-align:center; margin-top:1rem; font-size:0.75rem; color:var(--text-soft);">
            📡 Data diperbarui secara real-time dari sensor IoT
        </div>
    """, unsafe_allow_html=True)
