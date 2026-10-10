import os

import httpx
import streamlit as st
from model_settings import settings_panel
from presentation import CATEGORIES, show_answer, source_label, source_location
from text import INPUT_DIRECTION, text_html

st.set_page_config(page_title="PinuiRAG", layout="wide")
st.title("PinuiRAG")
st.caption("Поиск по документам на иврите и ответы на языке обращения")
st.html(INPUT_DIRECTION, unsafe_allow_javascript=True)
BASE = os.environ.get("API_BASE_URL", "http://api:8000").rstrip("/")


def call(method, route, body=None):
    response = httpx.request(method, BASE + route, json=body, timeout=95)
    result = response.json()
    if response.status_code >= 400:
        raise ValueError(result.get("error", {}).get("code", "SERVICE_UNAVAILABLE"))
    return result


def show_source(source, side="search", number=None):
    with st.container(border=True):
        st.html(f"<span id='source-{side}-{source['citation_id']}'></span>")
        label = source_label(source)
        st.markdown(f"**[{number}] {label}**" if number else f"**{label}**")
        st.caption(source_location(source))
        if source.get("quote_translation"):
            st.caption("Перевод короткой цитаты")
            st.html(text_html(source["quote_translation"]))
        else:
            reason = source.get("quote_translation_error")
            if reason == "DAILY_BUDGET_EXCEEDED":
                st.caption(
                    "Перевод цитаты отложен: достигнут дневной лимит расходов. Оригинал — ниже."
                )
            elif reason == "BUDGET_EXCEEDED":
                st.caption(
                    "Перевод цитаты не выполнен: достигнут лимит расходов на запрос. "
                    "Оригинал — ниже."
                )
            else:
                st.caption("Оригинал цитаты доступен ниже; перевод не подготовлен.")
        with st.expander("Цитата на иврите и сведения об источнике"):
            if source.get("quote_excerpt"):
                st.caption("Короткая выдержка из оригинала")
                st.html(text_html(source["quote_excerpt"]))
            st.caption("Полный найденный фрагмент")
            st.html(text_html(source["quote"]))
            st.caption(source["title"])
            version = source.get("version_label") or source.get("publication_date")
            st.caption(f"Редакция: {version or 'не установлена'} · {source_location(source)}")
            st.caption(
                f"Автор: {source['issuer']} · Тип: {CATEGORIES.get(source['category'], 'Документ')}"
            )
            st.caption(
                "Актуальность подтверждена"
                if source["verification_status"] == "verified"
                else "Актуальность не подтверждена; источник требует проверки"
            )
            if source.get("locator", {}).get("extraction_method") == "ocr":
                st.caption("OCR: распознанный текст; сверяйте с исходной страницей")
            if source.get("source_url", "").startswith("https://"):
                st.link_button("Официальный источник", source["source_url"])
            for position, provenance in enumerate(source.get("provenance", [])):
                st.link_button(
                    f"{provenance['title']} · пункт {provenance['clause']}",
                    provenance["url"],
                    key=side + source["citation_id"] + str(position),
                )
            if not source.get("is_derived_text") and st.button(
                "Открыть оригинал", key=side + source["citation_id"]
            ):
                response = httpx.get(
                    BASE + f"/documents/{source['document_id']}/original", timeout=30
                )
                if response.status_code == 200:
                    extension = ".docx" if source.get("document_type") == "docx" else ".pdf"
                    st.download_button(
                        "Скачать документ",
                        response.content,
                        file_name=source["document_id"] + extension,
                        key="download-" + side + source["citation_id"],
                    )
                else:
                    st.error("Оригинал недоступен")


try:
    status = httpx.get(BASE + "/status", timeout=10).json()
except (httpx.HTTPError, ValueError):
    st.error("Сервис недоступен")
    st.stop()


def clear_results():
    st.session_state.pop("query_result", None)
    st.session_state.pop("compare_result", None)


with st.sidebar:
    st.caption("Локальное приложение. Ключ модели при открытии не требуется.")
    settings_panel(call, status["capabilities"]["llm_configured"])
    with st.expander("Состояние"):
        st.table(
            [
                {"Компонент": name, "Состояние": value["status"]}
                for name, value in status["components"].items()
            ]
        )

if not status["capabilities"]["llm_configured"]:
    st.info(
        "Без ключа доступен поиск на иврите с оригинальными выде"
        "ржками. Перевод, ответы и сравнение требуют настройки G"
        "PT-5.4 mini на сервере."
    )
try:
    documents = call("GET", "/documents")["documents"]
except (httpx.HTTPError, ValueError) as exc:
    st.error(str(exc) if isinstance(exc, ValueError) else "Сервис недоступен")
    st.stop()

by_id = {d["document_id"]: d for d in documents}
if any(
    source["document_id"] not in by_id
    for source in st.session_state.get("query_result", {}).get("sources", [])
):
    clear_results()
if any(
    source["document_id"] not in by_id
    for finding in st.session_state.get("compare_result", {}).get("findings", [])
    for source in finding.get("citations_a", []) + finding.get("citations_b", [])
):
    clear_results()
if not by_id:
    st.info("Нет доступных документов")
    st.stop()
search_tab, compare_tab, registry_tab, upload_tab = st.tabs(
    ["Поиск и ответы", "Тематическое сравнение", "Реестр", "Загрузка и задания"]
)

with search_tab:
    with st.form("query"):
        question = st.text_area("Вопрос", placeholder="מי משלם את שכר השמאי?")
        selected = st.multiselect(
            "Документы", list(by_id), format_func=lambda key: by_id[key]["title"]
        )
        response_mode = st.selectbox(
            "Режим ответа",
            ["auto", "search", "answer"],
            format_func={
                "auto": "Ответ с источниками (авто)",
                "search": "Только поиск цитат на иврите",
                "answer": "Ответ с объяснением",
            }.get,
        )
        mode = st.selectbox(
            "Область",
            [
                "all_documents",
                "current_norms",
                "public_documents",
                "project_documents",
                "historical",
            ],
            format_func={
                "all_documents": "Все документы, включая договоры",
                "current_norms": "Действующие подтверждённые нормы",
                "public_documents": "Общие документы, включая рекомендации",
                "project_documents": "Выбранные документы проекта",
                "historical": "Исторический правовой снимок",
            }.get,
        )
        if mode == "all_documents":
            st.caption(
                "Поиск в законах, рекомендациях и договорах. Тип и актуальность каждого "
                "источника указаны отдельно. Непроверенные цепочки законов исключены."
            )
        if mode == "current_norms":
            st.caption(
                "Здесь доступны только подтверждённые нормы. Для вопросов об адвокате "
                "или организаторе можно выбрать общие документы с рекомендациями; "
                "они не приравниваются к закону."
            )
        if mode == "public_documents":
            st.caption(
                "Рекомендации и образцы не являются законом. Проверяйте тип и статус источника."
            )
        as_of = st.date_input("Дата правового снимка") if mode == "historical" else None
        if selected:
            st.caption(
                "Для выбранных рекомендаций или договоров используйте pr"
                "oject_documents. current_norms использует только подтве"
                "рждённые нормы."
            )
        submitted = st.form_submit_button("Найти")
    if submitted:
        try:
            with st.spinner("Поиск по выбранным документам"):
                st.session_state["query_result"] = call(
                    "POST",
                    "/query",
                    {
                        "question": question,
                        "document_ids": (
                            [
                                key
                                for key in (selected or list(by_id))
                                if not by_id[key]["project_id"]
                            ]
                            if mode == "public_documents"
                            else selected
                        ),
                        "response_mode": response_mode,
                        "mode": "project_documents" if mode == "public_documents" else mode,
                        "as_of": as_of.isoformat() if as_of else None,
                    },
                )
        except (httpx.HTTPError, ValueError) as exc:
            st.session_state.pop("query_result", None)
            st.error(str(exc) if isinstance(exc, ValueError) else "Сервис недоступен")
    result = st.session_state.get("query_result")
    if result:
        if result["answer"]:
            show_answer(result, lambda value: st.html(text_html(value)))
        elif result["status"] == "search_results":
            st.subheader("Найденные фрагменты")
        if result["status"] == "insufficient_evidence":
            st.warning(
                "Недостаточно найденных данных. Это не доказывает отсутствие положения в документе."
            )
        for warning in result["warnings"]:
            st.caption(
                {
                    "LEGAL_CORPUS_INCOMPLETE": (
                        "Полные действующие редакции законов ещё не подтверждены. "
                        "Ответ отражает найденные документы и не подтверждает "
                        "полноту законодательства."
                    ),
                    "SOURCE_CURRENTNESS_UNCONFIRMED": (
                        "Актуальность части источников не подтверждена."
                    ),
                }.get(warning, warning)
            )
        if result["sources"]:
            st.subheader("Источники ответа" if result["answer"] else "Источники")
        for number, source in enumerate(result["sources"], 1):
            show_source(source, number=number)

with compare_tab:
    with st.form("compare"):
        a = st.selectbox("Договор A", list(by_id), format_func=lambda key: by_id[key]["title"])
        b = st.selectbox(
            "Договор B",
            list(by_id),
            index=min(1, len(by_id) - 1),
            format_func=lambda key: by_id[key]["title"],
        )
        topic = st.text_area(
            "Тема или конкретный вопрос", placeholder="Сравни условия предоставления парковки"
        )
        submitted = st.form_submit_button("Сравнить тему")
    if submitted:
        try:
            with st.spinner("Независимый поиск в двух договорах"):
                st.session_state["compare_result"] = call(
                    "POST", "/compare", {"question": topic, "document_a": a, "document_b": b}
                )
        except (httpx.HTTPError, ValueError) as exc:
            st.session_state.pop("compare_result", None)
            st.error(str(exc) if isinstance(exc, ValueError) else "Сервис недоступен")
    result = st.session_state.get("compare_result")
    if result:
        st.subheader("Сравнение по выбранной теме")
        if result["status"] == "clarification_required":
            st.info(
                "Укажите тему: площадь, парковка, сроки, гарантии или другой конкретный вопрос."
            )
        for finding in result.get("findings", []):
            left, right = st.columns(2)
            with left:
                st.markdown(
                    "**"
                    + (
                        source_label(finding["citations_a"][0])
                        if finding["citations_a"]
                        else "Документ А: данных не найдено"
                    )
                    + "**"
                )
                st.html(
                    text_html(
                        finding["statement_a"]
                        or "В найденных фрагментах A положение не подтверждено"
                    )
                )
                for source in finding["citations_a"]:
                    show_source(source, "A")
            with right:
                st.markdown(
                    "**"
                    + (
                        source_label(finding["citations_b"][0])
                        if finding["citations_b"]
                        else "Документ Б: данных не найдено"
                    )
                    + "**"
                )
                st.html(
                    text_html(
                        finding["statement_b"]
                        or "В найденных фрагментах B положение не подтверждено"
                    )
                )
                for source in finding["citations_b"]:
                    show_source(source, "B")
            if finding["difference"]:
                st.subheader("Различие")
                st.html(text_html(finding["difference"]))

with registry_tab:
    st.dataframe(documents, hide_index=True, width="stretch")
    st.caption(
        "Рекомендации и образцы договоров сохраняют собственный "
        "тип и статус. Полные актуальные тексты 16 законов ещё н"
        "е подтверждены."
    )

with upload_tab:
    import json
    from uuid import uuid4

    projects = call("GET", "/projects")["projects"]
    project_map = {p["project_id"]: p["title"] for p in projects}
    if project_map:
        with st.form("upload"):
            project = st.selectbox("Проект", list(project_map), format_func=project_map.get)
            uploaded = st.file_uploader("PDF или DOCX", type=["pdf", "docx"])
            title = st.text_input("Название документа")
            slug = st.text_input("Идентификатор семейства", placeholder="contract")
            version = st.text_input("Редакция", placeholder="08.2025")
            role = st.selectbox(
                "Роль документа", ["draft_contract", "contract", "signed_contract", "reference"]
            )
            submitted_upload = st.form_submit_button("Загрузить")
        if submitted_upload and uploaded:
            metadata = {
                "project_id": project,
                "title": title,
                "family_slug": slug,
                "version_label": version,
                "document_role": role,
                "category": "reference" if role == "reference" else "contract",
            }
            response = httpx.post(
                BASE + "/documents",
                files={"file": (uploaded.name, uploaded.getvalue())},
                data={"metadata": json.dumps(metadata)},
                headers={
                    "Idempotency-Key": str(uuid4()),
                },
                timeout=95,
            )
            if response.status_code == 202:
                st.session_state["last_job_id"] = response.json()["job_id"]
                st.success("Документ принят; обработка выполняется в фоне")
            else:
                st.error(response.json().get("error", {}).get("code", "UPLOAD_FAILED"))
    else:
        st.info("Нет проектов для загрузки документов.")
    identifier = st.text_input("ID задания", value=st.session_state.get("last_job_id", ""))
    if identifier and st.button("Проверить задание"):
        try:
            job = call("GET", "/jobs/" + identifier)
            st.json(job)
            st.progress(job["progress"])
        except (httpx.HTTPError, ValueError):
            st.error("Задание недоступно")
