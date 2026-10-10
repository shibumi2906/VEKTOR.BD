import pytest

from app.citations.presentation import correct_language, excerpt_options, present_sources
from app.services.errors import DomainError
from ui.presentation import answer_groups, source_label, source_location


def source(identifier="one", version="04.2025"):
    return {
        "citation_id": identifier,
        "document_id": version,
        "title": "מקור",
        "quote": "חניה אחת בסעיף 21.1",
        "category": "contract",
        "version_label": version,
        "locator": {"displayed_page": 3},
        "clause": "21.1",
    }


async def test_translated_excerpt_is_verbatim_and_original_is_unchanged():
    original = source()

    class Model:
        async def structured(self, instructions, data, schema, name):
            if name == "citation_excerpts":
                return {
                    "S1": {
                        "translation": "Одно парковочное место в пункте 21.1",
                        "title_translation": "Источник",
                    }
                }
            assert data["pairs"][0]["citation_id"] == "one"
            return {"accepted_ids": ["one"]}

    result = await present_sources(Model(), [original], [], "חניה", "ru")
    assert result[0]["quote"] == original["quote"]
    assert "quote_translation" not in original
    assert result[0]["quote_excerpt"] in original["quote"]
    assert result[0]["quote_translation"].startswith("Одно")


@pytest.mark.parametrize(
    "translation",
    [
        "Одна парковка в пункте 21.2",
        "One parking space in 21.1",
    ],
)
async def test_wrong_language_or_changed_number_is_not_shown(translation):
    class Model:
        async def structured(self, instructions, data, schema, name):
            assert name == "citation_excerpts"
            return {
                "S1": {
                    "translation": translation,
                    "title_translation": "Источник",
                }
            }

    originals = [source()]
    assert await present_sources(Model(), originals, [], "חניה", "ru") == originals


async def test_display_translation_budget_failure_keeps_validated_sources():
    class Model:
        async def structured(self, *args):
            raise DomainError("BUDGET_EXCEEDED", 429)

    originals = [source()]
    result = await present_sources(Model(), originals, [], "חניה", "ru")
    assert result[0]["quote"] == originals[0]["quote"]
    assert result[0]["quote_translation_error"] == "BUDGET_EXCEEDED"
    assert "quote_translation_error" not in originals[0]


def test_contract_versions_stay_separate_and_citations_are_attached():
    sources = [source(), source("two", "08.2025")]
    claims = [{"text": "А", "citation_ids": ["one"]}, {"text": "Б", "citation_ids": ["two"]}]
    groups = answer_groups(claims, sources)
    assert len(groups) == 2
    assert source_label(groups[0]["sources"][0]) == "Договор · 04.2025"
    assert source_label(groups[1]["sources"][0]) == "Договор · 08.2025"
    assert source_location(sources[0]) == "пункт 21.1 · страница 3"


def test_display_excerpts_never_rewrite_original_and_language_is_checked():
    quote = "טקסט מקור\n" * 80
    assert all(
        item["text"] in quote and len(item["text"]) <= 240 for item in excerpt_options(quote, "S1")
    )
    assert not correct_language("A lawyer represents owners", "ru")
    assert correct_language("Адвокат представляет собственников", "ru")
