"""Streamlit helpers shared by all pages."""
from __future__ import annotations

import os

import streamlit as st

from .fmp import FMPClient

GRADE_COLORS = {"A": "#1b9e4b", "B": "#7cb342", "C": "#f9a825", "D": "#ef6c00", "F": "#d32f2f"}
DISCLAIMER = "Educational tool, not investment advice. Models rely on estimates and free-plan data that can be incomplete or wrong."


def fmt_pct(x, d=1):
    return "—" if x is None or x != x else f"{x * 100:.{d}f}%"


def fmt_num(x, d=2, suffix=""):
    return "—" if x is None or x != x else f"{x:,.{d}f}{suffix}"


def fmt_money(x, d=2):
    return "—" if x is None or x != x else f"${x:,.{d}f}"


def fmt_big(x):
    if x is None or x != x:
        return "—"
    for div, s in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(x) >= div:
            return f"${x / div:,.2f}{s}"
    return f"${x:,.0f}"


def chip(grade: str) -> str:
    color = GRADE_COLORS.get(grade[:1], "#888")
    return f"<span style='background:{color};color:#fff;padding:2px 10px;border-radius:10px;font-weight:600'>{grade}</span>"


def _secret_key():
    try:
        return st.secrets.get("FMP_API_KEY")
    except Exception:
        return None


@st.cache_resource
def _client(key: str) -> FMPClient:
    return FMPClient(api_key=key)


def sidebar_api() -> FMPClient | None:
    """Render the API-key box + usage meter; return a client (or None without a key)."""
    with st.sidebar:
        st.subheader("Data source")
        default = st.session_state.get("fmp_key") or os.getenv("FMP_API_KEY") or _secret_key() or ""
        key = st.text_input("FMP API key", value=default, type="password",
                            help="Free key: financialmodelingprep.com (250 calls/day). Stored only in this session.")
        if key:
            st.session_state["fmp_key"] = key
        client = _client(key) if key else None
        if client:
            used = client.calls_today()
            st.progress(min(1.0, used / client.daily_budget), text=f"API calls today: {used}/{client.daily_budget}")
        else:
            st.info("Paste your free FMP API key to load data.")
        st.caption(DISCLAIMER)
    return client
