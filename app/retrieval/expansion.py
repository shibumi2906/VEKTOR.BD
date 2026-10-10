"""Bounded Hebrew glossary expansion; original text/numbers and scope are preserved."""

import re

GLOSSARY = {
    "שמאי": "שומה הערכת שווי",
    "חניה": "מקום חניה הצמדת חניה",
    "ערבות": "בטוחות ערבות בנקאית",
    "מארגן": "הסכם ארגון חובות מארגן",
    "עורך דין": "ייצוג משפטי שכר טרחה",
}


def expand_he(query, maximum=3):
    values = [query]
    for term, expansion in GLOSSARY.items():
        if re.search(r"(?<![א-ת])" + re.escape(term) + r"(?![א-ת])", query):
            values.append(query + " " + expansion)
            if len(values) >= maximum:
                break
    return values[:maximum]
