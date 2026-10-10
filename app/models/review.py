from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class DocumentReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    version_status: Literal["current", "superseded", "historical", "unknown"]
    legal_status: Literal["in_force", "repealed", "not_yet_effective", "unknown", "not_applicable"]
    verification_status: Literal["verified", "manual_review", "failed"]
    effective_from: date | None = None
    effective_to: date | None = None
    inventory_source_url: HttpUrl
    inventory_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_through: date
    notes: str = Field(min_length=10, max_length=4000)

    @field_validator("inventory_source_url")
    @classmethod
    def public_inventory(cls, url):
        from ipaddress import ip_address

        if url.username or url.password or not url.host or url.host == "localhost":
            raise ValueError("Public source URL required")
        try:
            address = ip_address(url.host.strip("[]"))
        except ValueError:
            return url
        if not address.is_global:
            raise ValueError("Public source URL required")
        return url
