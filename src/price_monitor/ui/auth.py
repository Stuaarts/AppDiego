from __future__ import annotations

import streamlit as st

from price_monitor.config import Settings
from price_monitor.security import verify_password
from price_monitor.ui.i18n import TEXT


def require_auth(settings: Settings) -> bool:
    if settings.auth_disabled:
        st.session_state["authenticated"] = True
        return True
    if st.session_state.get("authenticated"):
        return True
    st.title(TEXT["login_title"])
    with st.form("login_form"):
        password = st.text_input(TEXT["password"], type="password")
        submitted = st.form_submit_button(TEXT["login"])
    if submitted:
        if verify_password(password, settings.app_password_hash):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error(TEXT["invalid_password"])
    return False


def render_logout(settings: Settings) -> None:
    if settings.auth_disabled:
        return
    if st.sidebar.button(TEXT["logout"]):
        st.session_state.clear()
        st.rerun()
