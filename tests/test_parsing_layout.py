import zipfile
from uuid import uuid4

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.chunking.core import parse_pages
from app.parsing.docx import W, formatted_number, parse_docx
from app.parsing.layout import attach_tables, unique_range


def test_cell_alignment_rejects_duplicates_and_preserves_original_order():
    assert unique_range("before חניה  21.1 after", "חניה 21.1") == (7, 17)
    assert unique_range("חניה חניה", "חניה") is None
    assert unique_range("חניה", "הינח") == (0, 4)


def test_real_pdf_table_geometry_and_exact_page_coverage(tmp_path):
    writer = PdfWriter()
    page = writer.add_blank_page(300, 300)
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"0 0 0 RG 30 100 240 100 re S 150 100 m 150 200 l S "
        b"30 150 m 270 150 l S BT /F1 12 Tf 40 175 Td (alpha) Tj "
        b"120 0 Td (beta) Tj -120 -50 Td (gamma) Tj 120 0 Td (delta) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    path = tmp_path / "table.pdf"
    writer.write(path)
    text = PdfReader(path).pages[0].extract_text()
    revision, blocks, _ = parse_pages(str(uuid4()), [text], "a" * 64)
    result, warnings = attach_tables(path, [text], revision, blocks)
    assert not warnings
    cells = [b for b in result if b["locator"].get("table_id")]
    assert len(cells) == 4
    assert {b["original_text"] for b in cells} == {"alpha", "beta", "gamma", "delta"}
    assert all(len(b["locator"]["bbox"]) == 4 for b in cells)
    assert "".join(b["original_text"] for b in result) == text
    for block in result:
        locator = block["locator"]
        assert text[locator["page_char_start"] : locator["page_char_end"]] == block["original_text"]


def test_docx_partial_style_numbering_inherits_id_and_formats_parent(tmp_path):
    path = tmp_path / "styles.docx"
    namespace = W[1:-1]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            f'''<w:document xmlns:w="{namespace}"><w:body>
        <w:p><w:pPr><w:pStyle w:val="Child"/><w:numPr><w:ilvl w:val="1"/></w:numPr></w:pPr>
        <w:r><w:t>חניה</w:t></w:r></w:p></w:body></w:document>''',
        )
        archive.writestr(
            "word/styles.xml",
            f'''<w:styles xmlns:w="{namespace}">
        <w:style w:styleId="Base"><w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr></w:style>
        <w:style w:styleId="Child"><w:basedOn w:val="Base"/></w:style></w:styles>''',
        )
        archive.writestr(
            "word/numbering.xml",
            f'''<w:numbering xmlns:w="{namespace}">
        <w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="4"/>
        <w:numFmt w:val="upperRoman"/></w:lvl><w:lvl w:ilvl="1"><w:start w:val="2"/>
        <w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%1.%2"/></w:lvl></w:abstractNum>
        <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>''',
        )
    _, _, blocks, _, warnings = parse_docx(str(uuid4()), path)
    assert blocks[0]["clause"] == "IV.b"
    assert not warnings
    assert formatted_number(27, "upperLetter") == "AA"
    assert formatted_number(15, "hebrew1") == "טו"
    assert formatted_number(16, "hebrew1") == "טז"


def test_overlapping_citations_union_only_same_revision():
    from app.citations.builder import merge_overlapping

    block, doc, revision = (str(uuid4()) for _ in range(3))
    base = {
        "document_id": doc,
        "parsing_revision": revision,
        "block_id": block,
        "chunk_id": str(uuid4()),
        "span_start": 0,
        "span_end": 5,
        "quote": "abcde",
    }
    second = {**base, "chunk_id": str(uuid4()), "span_start": 3, "span_end": 8, "quote": "defgh"}
    other = {**base, "parsing_revision": str(uuid4())}
    result = merge_overlapping([second, base, other])
    assert len(result) == 2
    assert result[0]["quote"] == "abcdefgh"
    assert result[0]["span_end"] == 8
    assert len(result[0]["chunk_ids"]) == 2
