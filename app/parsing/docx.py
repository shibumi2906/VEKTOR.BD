"""Safe OOXML body-order parser with list counters and nested table locators."""

import re
import xml.etree.ElementTree as ET
import zipfile
from uuid import UUID, uuid5

from app.chunking.core import CLAUSE, digest
from app.registry.legal_engine import canonical_hash

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def xml(archive, name):
    raw = archive.read(name)
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ValueError("XML entities are not allowed")
    return ET.fromstring(raw)


def val(node, name, default=None):
    item = node.find(W + name) if node is not None else None
    return item.get(W + "val", default) if item is not None else default


def formatted_number(number, fmt):
    if fmt == "decimal":
        return str(number)
    if fmt == "decimalZero":
        return f"{number:02d}"
    if fmt in ("lowerLetter", "upperLetter"):
        value = ""
        while number > 0:
            number, digit = divmod(number - 1, 26)
            value = chr(65 + digit) + value
        return value.lower() if fmt == "lowerLetter" else value
    if fmt in ("lowerRoman", "upperRoman") and 0 < number < 4000:
        value = ""
        for amount, symbol in (
            (1000, "M"),
            (900, "CM"),
            (500, "D"),
            (400, "CD"),
            (100, "C"),
            (90, "XC"),
            (50, "L"),
            (40, "XL"),
            (10, "X"),
            (9, "IX"),
            (5, "V"),
            (4, "IV"),
            (1, "I"),
        ):
            count, number = divmod(number, amount)
            value += symbol * count
        return value.lower() if fmt == "lowerRoman" else value
    if fmt == "hebrew1" and 0 < number < 1000:
        value = ""
        for amount, symbol in (
            (400, "ת"),
            (300, "ש"),
            (200, "ר"),
            (100, "ק"),
            (90, "צ"),
            (80, "פ"),
            (70, "ע"),
            (60, "ס"),
            (50, "נ"),
            (40, "מ"),
            (30, "ל"),
            (20, "כ"),
        ):
            count, number = divmod(number, amount)
            value += symbol * count
        if number in (15, 16):
            return value + ("טו" if number == 15 else "טז")
        tens, units = divmod(number, 10)
        return value + "י" * tens + ("אבגדהוזחט"[units - 1] if units else "")
    raise ValueError("Unsupported numbering format")


def parse_docx(document_id, path):
    fingerprint = canonical_hash({"parser": "ooxml-body-order-v2", "normalization": "identity-v1"})
    revision = str(uuid5(UUID(document_id), fingerprint))
    blocks, paragraphs, warnings = [], {}, []
    with zipfile.ZipFile(path) as archive:
        if (
            len(archive.infolist()) > 10000
            or sum(i.file_size for i in archive.infolist()) > 100_000_000
        ):
            raise ValueError("DOCX uncompressed limit exceeded")
        if any(i.file_size > max(i.compress_size, 1) * 2000 for i in archive.infolist()):
            raise ValueError("DOCX compression ratio exceeded")
        body = xml(archive, "word/document.xml").find(W + "body")
        numbering = (
            xml(archive, "word/numbering.xml")
            if "word/numbering.xml" in archive.namelist()
            else ET.Element("empty")
        )
        abstracts = {n.get(W + "abstractNumId"): n for n in numbering.findall(W + "abstractNum")}
        nums = {n.get(W + "numId"): n for n in numbering.findall(W + "num")}
        styles = (
            xml(archive, "word/styles.xml")
            if "word/styles.xml" in archive.namelist()
            else ET.Element("empty")
        )
        stylemap = {n.get(W + "styleId"): n for n in styles.findall(W + "style")}
        counters, clause, group, paragraph_index, table_index = {}, None, 0, 0, 0

        def num_properties(node, seen=None):
            seen = seen or set()
            properties = node.find(W + "pPr") if node is not None else None
            number = properties.find(W + "numPr") if properties is not None else None
            style = val(properties, "pStyle") or val(node, "basedOn")
            inherited = {}
            if style and style not in seen:
                inherited = num_properties(stylemap.get(style), seen | {style})
            return {
                **inherited,
                **{
                    key: val(number, key)
                    for key in ("numId", "ilvl")
                    if val(number, key) is not None
                },
            }

        def list_label(node):
            properties = num_properties(node)
            num_id, level = properties.get("numId"), int(properties.get("ilvl", "0"))
            if not num_id or num_id == "0" or num_id not in nums:
                return None
            num = nums[num_id]
            abstract = abstracts.get(val(num, "abstractNumId"))
            if abstract is None:
                warnings.append("NUMBERING_DEFINITION_MISSING")
                return None
            levels = {int(n.get(W + "ilvl")): n for n in abstract.findall(W + "lvl")}
            for override in num.findall(W + "lvlOverride"):
                nested = override.find(W + "lvl")
                if nested is not None:
                    levels[int(override.get(W + "ilvl"))] = nested
            current = levels.get(level)
            if current is None:
                return None
            start = int(val(current, "start", "1"))
            for override in num.findall(W + "lvlOverride"):
                if int(override.get(W + "ilvl")) == level:
                    start = int(val(override, "startOverride", str(start)))
            key = (num_id, level)
            counters[key] = counters.get(key, start - 1) + 1
            for deeper in range(level + 1, 9):
                definition = levels.get(deeper)
                restart = val(definition, "lvlRestart")
                if restart != "0" and (restart is None or int(restart) == level + 1):
                    counters.pop((num_id, deeper), None)
            if val(current, "numFmt") in ("bullet", "none"):
                return None
            template = val(current, "lvlText", "%1.")

            def substitute(match):
                referenced = int(match.group(1)) - 1
                definition = levels.get(referenced)
                return formatted_number(
                    counters.get((num_id, referenced), int(val(definition, "start", "1"))),
                    val(definition, "numFmt", "decimal"),
                )

            try:
                return re.sub(r"%(\d)", substitute, template).strip(". ")
            except ValueError:
                warnings.append("UNSUPPORTED_LIST_LABEL_REQUIRES_REVIEW")
                return None

        def walk(parent, table=None, row=None, cell=None):
            nonlocal clause, group, paragraph_index, table_index
            for node in parent:
                if node.tag == W + "p":
                    paragraph_index += 1
                    text = "".join(
                        n.text or "" if n.tag == W + "t" else "\t" if n.tag == W + "tab" else "\n"
                        for n in node.iter()
                        if n.tag in (W + "t", W + "tab", W + "br")
                    )
                    label = list_label(node)
                    match = CLAUSE.match(text)
                    if match:
                        label = match.group(1).rstrip(".")
                    if label:
                        clause = label
                        group += 1
                    if not text.strip():
                        continue
                    if not clause or table is not None:
                        group += 1
                    paragraph_id = f"p{paragraph_index}"
                    paragraphs[paragraph_id] = text
                    block_id = str(uuid5(UUID(revision), paragraph_id + ":" + digest(text)))
                    locator = {
                        "pdf_page_index": None,
                        "displayed_page": None,
                        "printed_page_number": None,
                        "paragraph_id": paragraph_id,
                        "table_id": table,
                        "row_index": row,
                        "cell_index": cell,
                        "bbox": None,
                        "page_char_start": None,
                        "page_char_end": None,
                    }
                    blocks.append(
                        {
                            "block_id": block_id,
                            "ordinal": len(blocks),
                            "original_text": text,
                            "search_text": text,
                            "normalization_map": "identity-v1",
                            "locator": locator,
                            "clause": clause,
                            "section": clause.split(".")[0] if clause else None,
                            "group": group,
                            "excluded": False,
                            "structure_confidence": "medium" if label else "low",
                        }
                    )
                elif node.tag == W + "tbl":
                    table_index += 1
                    table_id = f"t{table_index}"
                    for row_index, tr in enumerate(node.findall(W + "tr")):
                        for cell_index, tc in enumerate(tr.findall(W + "tc")):
                            walk(tc, table_id, row_index, cell_index)
                elif node.tag in (W + "sdt", W + "sdtContent"):
                    walk(node, table, row, cell)

        walk(body)
    return revision, fingerprint, blocks, paragraphs, sorted(set(warnings))
