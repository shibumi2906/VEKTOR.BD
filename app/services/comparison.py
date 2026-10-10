import re
from uuid import uuid4

from app.citations.presentation import present_sources
from app.llm.provider import STRING, Provider, object_schema
from app.models.query import QueryRequest
from app.services.errors import DomainError
from app.services.query import answer, language, translate


async def compare(connection, actor, retrieval, settings, request, request_id):
    if request.document_a == request.document_b:
        raise DomainError("SAME_DOCUMENT", 422)
    if request.debug and actor["role"] != "admin":
        raise DomainError("FORBIDDEN", 403)
    if request.debug and not settings.enable_debug:
        raise DomainError("DEBUG_DISABLED", 403)
    topic = request.question.strip()
    queries = [
        QueryRequest(question=topic, document_ids=[identifier], mode="project_documents")
        for identifier in (request.document_a, request.document_b)
    ]
    scopes = [await retrieval.scope(connection, actor, q) for q in queries]
    generic = re.fullmatch(
        (
            "(?:сравни|сравните|чем отличаются|compare|השווה|מה ההבד"
            "ל)(?:\\s+(?:договоры|два договора|contracts|הסכמים))?[? "
            ".]*"
        ),
        topic,
        re.I,
    )
    stripped = re.sub(r"\d+(?:[./]\d+)*", "", topic.casefold())
    stripped = re.sub(
        (
            "сравни(?:те)?|чем|отличаются|договор(?:ы|а)?|версии|com"
            "pare|contracts|השווה|מה|ההבדל|בין|הסכמים|החוזים|\\bи\\b"
        ),
        "",
        stripped,
    )
    if generic or not re.search(r"[А-Яа-яЁёא-תa-z]", stripped):
        return {
            "request_id": str(request_id),
            "status": "clarification_required",
            "findings": [],
            "clarification_topics": ["Площадь", "Парковка", "Сроки", "Гарантии"],
            "usage": [],
        }
    if not settings.llm_configured:
        raise DomainError("LLM_NOT_CONFIGURED")
    selected_language = language(request, settings)
    provider = Provider(settings, connection, request_id, settings.topic_compare_cost_limit)
    queries = [
        QueryRequest(
            question=topic,
            document_ids=[identifier],
            mode="project_documents",
            language=selected_language,
            response_mode="answer",
        )
        for identifier in (request.document_a, request.document_b)
    ]
    query = topic if selected_language == "he" else await translate(provider, topic)
    findings = []
    results = []
    for q, scope in zip(queries, scopes, strict=True):
        chunks = await retrieval.search(connection, actor, scope, query)
        claims, sources = (
            await answer(connection, provider, q, chunks, selected_language) if chunks else ([], [])
        )
        results.append((claims, sources))
    (claims_a, sources_a), (claims_b, sources_b) = results
    difference = None
    if claims_a and claims_b:
        proposal = await provider.structured(
            "Compare ONLY the already validated statements A and B on the specified topic. "
            + (
                "Do not infer absence of provisions. Return a concise su"
                "pported difference in the user's language."
            ),
            {"topic": topic, "language": selected_language, "A": claims_a, "B": claims_b},
            object_schema({"difference": STRING}),
            "topic_difference",
        )
        verdict = await provider.structured(
            (
                "Is the proposed difference fully entailed by statements"
                " A and B? Reject unsupported facts. "
            )
            + "Return supported true only when fully supported.",
            {"difference": proposal["difference"], "A": claims_a, "B": claims_b},
            object_schema({"supported": {"type": "boolean"}}),
            "difference_validation",
        )
        if verdict["supported"]:
            difference = proposal["difference"]
    if selected_language != "he":
        combined = await present_sources(
            provider, sources_a + sources_b, claims_a + claims_b, topic, selected_language
        )
        translated = {s["citation_id"]: s for s in combined}
        sources_a = [translated[s["citation_id"]] for s in sources_a]
        sources_b = [translated[s["citation_id"]] for s in sources_b]
    for scope in scopes:
        await retrieval.revalidate(connection, actor, scope)
    findings.append(
        {
            "topic": topic,
            "statement_a": "\n".join(c["text"] for c in claims_a) or None,
            "statement_b": "\n".join(c["text"] for c in claims_b) or None,
            "difference": difference,
            "citations_a": sources_a,
            "citations_b": sources_b,
            "evidence_status_a": "found" if claims_a else "not_found_in_retrieval",
            "evidence_status_b": "found" if claims_b else "not_found_in_retrieval",
        }
    )
    report = {
        "request_id": str(request_id),
        "status": "compared" if difference else "insufficient_evidence",
        "language": selected_language,
        "findings": findings,
        "usage": provider.usage,
        "warnings": [] if difference else ["INSUFFICIENT_RETRIEVED_EVIDENCE"],
        "snapshots": [[str(item["generation"]) for item in scope] for scope in scopes],
    }
    import json

    await connection.execute(
        "INSERT INTO registry.comparison_reports VALUES($1,$2,$3,$4,$5,now())",
        uuid4(),
        actor["actor_id"],
        request.document_a,
        request.document_b,
        json.dumps(report, ensure_ascii=False),
    )
    return report
