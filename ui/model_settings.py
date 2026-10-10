"""Simple credential entry for the local application."""

import httpx
import streamlit as st

ERRORS = {
    "INVALID_API_KEY": "Ключ не принят OpenAI. Проверьте, что скопировали его целиком.",
    "MODEL_ACCESS_DENIED": "У этого ключа нет доступа к GPT-5.4 mini.",
    "KEY_CHECK_UNAVAILABLE": "Не удалось связаться с OpenAI. Проверьте интернет и повторите.",
    "KEY_CHECK_RATE_LIMITED": "OpenAI временно ограничил проверки. Повторите позже.",
    "KEY_SAVE_FAILED": "Не удалось сохранить ключ на компьютере.",
    "LLM_NOT_CONFIGURED": "Сначала добавьте API-ключ.",
    "VALIDATION_ERROR": "Введите полный API-ключ без пробелов внутри.",
}


def settings_panel(call, configured):
    with st.expander("Настройки GPT-5.4 mini", expanded=not configured):
        st.caption("API-ключ сохранён" if configured else "API-ключ ещё не добавлен")
        if st.session_state.pop("key_saved_message", False):
            st.success("Ключ сохранён. Доступ к GPT-5.4 mini подтверждён.")
        st.caption(
            "Ключ хранится на этом компьютере. Проверка отправляет его только в OpenAI. "
            "Проверка доступа не подтверждает наличие средств для ответов."
        )
        st.link_button("Получить API-ключ в OpenAI", "https://platform.openai.com/api-keys")
        with st.form("openai_key_settings", clear_on_submit=True):
            key = st.text_input("API-ключ OpenAI", type="password", placeholder="Вставьте ключ")
            submitted = st.form_submit_button("Проверить и сохранить", use_container_width=True)
        if submitted:
            if not key.strip():
                st.error("Вставьте API-ключ в поле выше.")
            else:
                try:
                    with st.spinner("Проверка подключения к OpenAI…"):
                        call("POST", "/settings/openai", {"api_key": key})
                    st.session_state["key_saved_message"] = True
                    st.rerun()
                except ValueError as exc:
                    st.error(ERRORS.get(str(exc), "Не удалось сохранить ключ. Повторите попытку."))
                except httpx.HTTPError:
                    st.error("Локальный сервис недоступен. Повторите попытку.")
        if configured and st.button("Проверить сохранённый ключ", use_container_width=True):
            try:
                with st.spinner("Проверка подключения к OpenAI…"):
                    call("POST", "/settings/openai/check")
                st.success("Доступ к GPT-5.4 mini подтверждён.")
            except ValueError as exc:
                st.error(ERRORS.get(str(exc), "Не удалось проверить ключ."))
            except httpx.HTTPError:
                st.error("Локальный сервис недоступен. Повторите попытку.")
