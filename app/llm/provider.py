"""Responses API with strict schemas, explicit errors and conservative request budgets."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx

from app.services.errors import DomainError


class Provider:
    def __init__(self, settings, connection, request_id, limit=None):
        self.settings, self.connection, self.request_id = settings, connection, request_id
        self.limit = limit if limit is not None else settings.query_cost_limit
        self.spent = 0.0
        self.usage = []

    async def structured(self, instructions, data, schema, name):
        if not self.settings.llm_configured:
            raise DomainError("LLM_NOT_CONFIGURED")
        if not self.limit or not self.settings.max_output_tokens:
            raise DomainError("LLM_BUDGET_NOT_CONFIGURED")
        text = json.dumps(data, ensure_ascii=False)
        # UTF-8 bytes upper-bound text tokens; conservatively reserve all output each attempt.
        maximum_input = len((instructions + text + json.dumps(schema)).encode("utf-8"))
        if maximum_input > (self.settings.max_context_tokens or 16000):
            raise DomainError("CONTEXT_LIMIT_EXCEEDED")
        prices = json.loads(Path("config/provider-prices.json").read_text())["models"]
        model = self.settings.llm_model
        for attempt in range(self.settings.provider_max_attempts):
            if model not in prices:
                raise DomainError("MODEL_PRICE_NOT_CONFIGURED")
            input_price, output_price = prices[model]["input"], prices[model]["output"]
            reserved = (
                maximum_input * input_price + self.settings.max_output_tokens * output_price
            ) / 1e6
            if self.spent + reserved > self.limit:
                raise DomainError("BUDGET_EXCEEDED", 429)
            # Reservations include failed/ambiguous calls; retry never resets consumed budget.
            self.spent += reserved
            async with self.connection.transaction():
                await self.connection.execute("SELECT pg_advisory_xact_lock(210028)")
                today = await self.connection.fetchval(
                    """SELECT COALESCE(sum(reserved_usd),0) FROM registry.provider_reservations
                    WHERE (created_at AT TIME ZONE 'Asia/Jerusalem')::date=
                    (now() AT TIME ZONE 'Asia/Jerusalem')::date"""
                )
                if today + reserved > self.settings.daily_cost_limit:
                    raise DomainError("DAILY_BUDGET_EXCEEDED", 429)
                await self.connection.execute(
                    "INSERT INTO registry.provider_reservations VALUES($1,$2,$3,$4,now())",
                    uuid4(),
                    self.request_id,
                    model,
                    reserved,
                )
            body = {
                "model": model,
                "store": False,
                "instructions": instructions,
                "input": text,
                "max_output_tokens": self.settings.max_output_tokens,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": name,
                        "schema": schema,
                        "strict": True,
                    }
                },
            }
            try:
                async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                    response = await client.post(
                        "https://api.openai.com/v1/responses",
                        json=body,
                        headers={
                            "Authorization": "Bearer "
                            + self.settings.openai_api_key.get_secret_value()
                        },
                    )
            except httpx.HTTPError as exc:
                raise DomainError("PROVIDER_UNAVAILABLE", 503) from exc
            if response.status_code in (429, 500, 502, 503, 504):
                if response.status_code != 429:
                    model = self.settings.llm_fallback_model
                if attempt + 1 < self.settings.provider_max_attempts:
                    await asyncio.sleep(min(2**attempt, 4))
                    continue
                raise DomainError("PROVIDER_UNAVAILABLE", 503)
            if response.status_code != 200:
                raise DomainError("PROVIDER_CONFIGURATION_ERROR", 502)
            payload = response.json()
            usage = payload.get("usage") or {}
            record = {
                "provider": "openai",
                "model": model,
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "cached_input_tokens": usage.get("input_tokens_details", {}).get("cached_tokens"),
                "estimated_cost": None,
                "currency": "USD",
            }
            if record["input_tokens"] is not None and record["output_tokens"] is not None:
                record["estimated_cost"] = (
                    record["input_tokens"] * input_price + record["output_tokens"] * output_price
                ) / 1e6
            self.usage.append(record)
            await self.connection.execute(
                "INSERT INTO registry.provider_usage VALUES($1,$2,$3,$4,now())",
                uuid4(),
                self.request_id,
                model,
                json.dumps(record),
            )
            if payload.get("status") != "completed":
                raise DomainError("PROVIDER_INCOMPLETE_RESPONSE", 502)
            texts = [
                c["text"]
                for item in payload.get("output", [])
                for c in item.get("content", [])
                if c.get("type") == "output_text"
            ]
            if not texts:
                raise DomainError("PROVIDER_REFUSAL", 502)
            try:
                result = json.loads("".join(texts))
                validate_schema(result, schema)
                return result
            except ValueError as exc:
                raise DomainError("PROVIDER_INVALID_OUTPUT", 502) from exc
        raise DomainError("PROVIDER_UNAVAILABLE", 503)


def validate_schema(value, schema):
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError("Output value outside allowed evidence IDs")
    kind = schema["type"]
    if kind == "object":
        if not isinstance(value, dict) or set(value) != set(schema["properties"]):
            raise ValueError("Unexpected structured output fields")
        for key, child in schema["properties"].items():
            validate_schema(value[key], child)
    elif kind == "array":
        if not isinstance(value, list) or len(value) > 100:
            raise ValueError("Invalid output array")
        for item in value:
            validate_schema(item, schema["items"])
    elif kind == "string":
        if not isinstance(value, str):
            raise ValueError("Invalid output string")
    elif kind == "integer":
        if type(value) is not int:
            raise ValueError("Invalid output integer")
    elif kind == "boolean":
        if type(value) is not bool:
            raise ValueError("Invalid output boolean")
    else:
        raise ValueError("Unsupported output schema")


def object_schema(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


STRING = {"type": "string"}


def claims_schema(evidence_ids):
    claim = object_schema(
        {
            "claim_id": STRING,
            "text": STRING,
            "evidence_ids": {"type": "array", "items": {"type": "string", "enum": evidence_ids}},
        }
    )
    return object_schema({"claims": {"type": "array", "items": claim}})
