import time

import streamlit as st


def fmt_sec(sec: int) -> str:
    sec = max(0, int(sec or 0))
    m, s = divmod(sec, 60)
    return f"{m:02d}:{s:02d}"


def trigger_autorefresh(enabled: bool) -> None:
    """Refresh page periodically so countdown bergerak tanpa loop ketat."""
    if not enabled:
        return
    auto_fn = getattr(st, "autorefresh", None)
    if callable(auto_fn):
        auto_fn(interval=5000, key="auto-refresh")
    else:
        time.sleep(5)
        st.rerun()
