import pytest

from app.llm.terminology import terminology
from app.services.errors import DomainError
from app.services.query import translate
from ui.text import INPUT_DIRECTION, text_html


async def test_lawyer_translation_preserves_role_and_receives_sources():
    class Model:
        async def structured(self, instructions, data, schema, name):
            assert data["terminology"][0]["term_he"] == "עורך דין המייצג בעלי דירות"
            assert data["terminology"][0]["source_url"].startswith("https://www.gov.il/")
            return {"search_question_he": "מה חובות עורך הדין המייצג את בעלי הדירות?"}

    assert "עורך הדין" in await translate(Model(), "Что должен делать адвокат жильцов?")


async def test_lawyer_cannot_be_translated_as_appraiser():
    class Model:
        async def structured(self, *args):
            return {"search_question_he": "מה חובות שמאי פינוי ובינוי כלפי בעלי הדירות?"}

    with pytest.raises(DomainError, match="TRANSLATION_UNAVAILABLE"):
        await translate(Model(), "Что должен делать адвокат жильцов?")


def test_glossary_is_not_legal_evidence_and_inputs_use_native_bidi():
    assert terminology("парковка") == []
    assert terminology("адвокат жильцов")[0]["source_type"] == "official_guidance"
    assert "dir='auto'" in text_html("מי משלם? 21.1")
    assert "&lt;script&gt;" in text_html("<script>")
    assert "setAttribute('dir', 'auto')" in INPUT_DIRECTION
