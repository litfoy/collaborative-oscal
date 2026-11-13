from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.domain.mappings import MappingCollection

ControlId = Annotated[str, Field(min_length=1, max_length=255)]
Relationship = Literal[
    "equal-to",
    "equivalent-to",
    "subset-of",
    "superset-of",
    "intersects-with",
    "no-relationship",
]
MatchingRationale = Literal["syntactic", "semantic", "functional"]


class MappingEntryInput(BaseModel):
    id: UUID | None = None
    sources: list[ControlId] = Field(min_length=1, max_length=1000)
    targets: list[ControlId] = Field(min_length=1, max_length=1000)
    relationship: Relationship
    matching_rationale: MatchingRationale
    justification: str = Field(default="", max_length=10000)

    @field_validator("sources", "targets")
    @classmethod
    def unique_members(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("A mapping set cannot contain duplicate controls.")
        return values


class MappingPairInput(BaseModel):
    id: UUID | None = None
    source_catalog_id: UUID
    source_revision_id: UUID
    target_catalog_id: UUID
    target_revision_id: UUID
    entries: list[MappingEntryInput] = Field(min_length=1, max_length=1000)


class MappingCollectionInput(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    mappings: list[MappingPairInput] = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Title must not be empty.")
        return title


class MappingEntryResponse(BaseModel):
    id: UUID
    relationship: str
    matching_rationale: str
    justification: str
    sources: list[str]
    targets: list[str]


class MappingPairResponse(BaseModel):
    id: UUID
    source_catalog_id: UUID
    source_revision_id: UUID
    target_catalog_id: UUID
    target_revision_id: UUID
    entries: list[MappingEntryResponse]


class MappingCollectionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    description: str
    oscal_version: str
    oscal_document_uuid: UUID
    version: str
    mappings: list[MappingPairResponse]
    created_by: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_collection(cls, value: MappingCollection) -> MappingCollectionResponse:
        collection = value.document["mapping-collection"]
        provenance = collection["provenance"]
        mappings = collection["mappings"]
        if isinstance(mappings, dict):
            mappings = [mappings]
        pairs = []
        for mapping in mappings:
            source_catalog_id, source_revision_id = _catalog_revision(
                mapping["source-resource"]["href"]
            )
            target_catalog_id, target_revision_id = _catalog_revision(
                mapping["target-resource"]["href"]
            )
            entries = mapping["maps"]
            if isinstance(entries, dict):
                entries = [entries]
            pairs.append(
                MappingPairResponse(
                    id=UUID(mapping["uuid"]),
                    source_catalog_id=source_catalog_id,
                    source_revision_id=source_revision_id,
                    target_catalog_id=target_catalog_id,
                    target_revision_id=target_revision_id,
                    entries=[
                        MappingEntryResponse(
                            id=UUID(entry["uuid"]),
                            relationship=entry["relationship"],
                            matching_rationale=(
                                entry.get("matching-rationale")
                                or mapping.get("matching-rationale")
                                or provenance["matching-rationale"]
                            ),
                            justification=entry.get("remarks", ""),
                            sources=[member["id-ref"] for member in entry["sources"]],
                            targets=[member["id-ref"] for member in entry["targets"]],
                        )
                        for entry in entries
                    ],
                )
            )
        return cls(
            id=value.id,
            tenant_id=value.tenant_id,
            title=collection["metadata"]["title"],
            description=provenance.get("mapping-description", ""),
            oscal_version=collection["metadata"]["oscal-version"],
            oscal_document_uuid=UUID(collection["uuid"]),
            version=collection["metadata"]["version"],
            mappings=pairs,
            created_by=value.created_by,
            updated_by=value.updated_by,
            created_at=value.created_at,
            updated_at=value.updated_at,
        )


class MappingCollectionListResponse(BaseModel):
    items: list[MappingCollectionResponse]
    total: int
    limit: int
    offset: int


class RelatedControlResponse(BaseModel):
    catalog_id: UUID
    catalog_name: str
    revision_id: UUID
    revision_number: int
    control_id: str
    title: str


class RelatedMappingResponse(BaseModel):
    collection_id: UUID
    collection_title: str
    mapping_uuid: UUID
    entry_uuid: UUID
    relationship: str
    matching_rationale: str
    matched_side: Literal["source", "target"]
    sources: list[RelatedControlResponse]
    targets: list[RelatedControlResponse]


class RelatedMappingListResponse(BaseModel):
    items: list[RelatedMappingResponse]


def _catalog_revision(href: str) -> tuple[UUID, UUID]:
    parts = href.strip("/").split("/")
    if (
        len(parts) != 9
        or parts[:3] != ["api", "v1", "tenants"]
        or parts[4] != "catalogs"
        or parts[6] != "revisions"
        or parts[8] != "export"
    ):
        raise RuntimeError("Mapping source reference does not match the stored revision.")
    return UUID(parts[5]), UUID(parts[7])
