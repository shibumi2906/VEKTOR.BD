"""Readable answer sections and references, independent of backend model prose."""

import streamlit as st

CATEGORIES = {
    "contract": "Договор",
    "official_guidance": "Официальные рекомендации",
    "guidance": "Рекомендации",
    "recommendation": "Рекомендации",
    "standard": "Стандарт",
    "law": "Закон",
    "consolidated_law": "Сводный текст закона",
    "regulation": "Подзаконный акт",
    "regulations": "Подзаконный акт",
    "template": "Образец договора",
    "contract_template": "Образец договора",
    "model_contract": "Образец договора",
    "model_agreement": "Образец договора",
    "form": "Форма",
    "ethics": "Материалы об адвокатской этике",
    "reference": "Справочный документ",
}


def source_label(source):
    category = CATEGORIES.get(source["category"], "Документ")
    if source.get("document_role") == "draft_contract":
        category = "Проект договора"
    version = source.get("version_label")
    if source["category"] == "contract":
        return category + (f" · {version}" if version else "")
    title = source.get("title_translation") or source["title"]
    return category + " · " + title[:150]


def source_location(source):
    locator = source.get("locator", {})
    parts = []
    if source.get("clause"):
        parts.append("пункт " + str(source["clause"]))
    if locator.get("displayed_page"):
        parts.append("страница " + str(locator["displayed_page"]))
    elif locator.get("paragraph_id"):
        parts.append("абзац " + str(locator["paragraph_id"]))
    if locator.get("table_id"):
        parts.append("таблица " + str(locator["table_id"]))
    return " · ".join(parts) or "место в исходном документе"


def answer_groups(claims, sources):
    lookup = {s["citation_id"]: s for s in sources}
    groups = {}
    for claim in claims:
        cited = [lookup[key] for key in claim["citation_ids"] if key in lookup]
        key = tuple(sorted({source["document_id"] for source in cited}))
        groups.setdefault(key, {"sources": cited, "claims": []})["claims"].append(claim)
    return list(groups.values())


def show_answer(result, render_text):
    numbers = {source["citation_id"]: i + 1 for i, source in enumerate(result["sources"])}
    st.subheader("Ответ")
    if not result.get("claims"):
        if result.get("answer"):
            render_text(result["answer"])
        return
    for group in answer_groups(result["claims"], result["sources"]):
        labels = list(dict.fromkeys(source_label(s) for s in group["sources"]))
        st.markdown("**" + " / ".join(labels) + "**")
        for claim in group["claims"]:
            render_text(claim["text"])
            refs = " · ".join(
                f"[{numbers[key]}](#source-search-{key})"
                for key in dict.fromkeys(claim["citation_ids"])
                if key in numbers
            )
            st.markdown("Источники: " + refs)
