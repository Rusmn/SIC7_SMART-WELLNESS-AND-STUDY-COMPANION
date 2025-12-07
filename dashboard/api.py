import json
import os
from typing import Any, Dict, Tuple

import requests
import streamlit as st

DEFAULT_API_BASE = os.environ.get("SWSC_API_BASE", "http://localhost:5000")


def get_base_url() -> str:
    return st.session_state.get("base_url", DEFAULT_API_BASE)


def set_base_url(url: str) -> None:
    st.session_state["base_url"] = url.rstrip("/")


def api_get(path: str) -> Tuple[Dict[str, Any], str]:
    try:
        resp = requests.get(f"{get_base_url()}{path}", timeout=5)
        resp.raise_for_status()
        return resp.json(), ""
    except Exception as exc:  # noqa: BLE001
        return {}, f"GET {path} error: {exc}"


def api_post(path: str, payload: Dict[str, Any]) -> str:
    try:
        resp = requests.post(
            f"{get_base_url()}{path}",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        resp.raise_for_status()
        return ""
    except Exception as exc:  # noqa: BLE001
        return f"POST {path} error: {exc}"


def api_get_plan(duration: int) -> Tuple[Dict[str, Any], str]:
    try:
        resp = requests.post(
            f"{get_base_url()}/plan",
            data=json.dumps({"duration_min": duration}),
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json(), ""
    except Exception as exc:  # noqa: BLE001
        return {}, f"Plan error: {exc}"
