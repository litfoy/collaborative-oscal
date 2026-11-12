import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from collaborative_oscal_oscal.catalog_import import (
    CatalogInputFormat,
    validate_catalog_bytes,
)
from collaborative_oscal_oscal.catalog_index import (
    canonical_json_sha256,
    project_catalog_indexes,
)
from collaborative_oscal_oscal.versions import (
    JSON_SCHEMA_OSCAL_VERSIONS,
    OSCAL_VERSION_ORDER,
    OscalDocumentModel,
    load_oscal_schema,
)
from sqlalchemy import func, select

from app.application.catalog_import import (
    CatalogImportMetadata,
    CatalogImportService,
    CatalogImportValidationError,
)
from app.domain.catalogs.models import CatalogOriginType, CatalogRevisionStatus
from app.domain.errors import EntityNotFoundError
from app.persistence.models import (
    CatalogControlIndexRecord,
    CatalogGroupIndexRecord,
    CatalogRecord,
    CatalogRevisionRecord,
)
from app.persistence.repositories import SQLAlchemyUnitOfWork

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "oscal_catalog.json"
NIST_CATALOG_PATH = Path(__file__).parent / "fixtures" / "NIST_SP-800-53_rev5_catalog-min.json"
BSI_CATALOG_PATH = (
    Path(__file__).parents[3] / "examples" / "catalogs" / "Grundschutz++-resolved_catalog.json"
)


def _catalog_document(oscal_version: str = "1.2.1") -> dict:
    document = json.loads(FIXTURE_PATH.read_text())
    document["catalog"]["metadata"]["oscal-version"] = oscal_version
    document["catalog"]["params"] = [
        {"id": "catalog_parameter", "label": "Example parameter", "values": ["enabled"]}
    ]
    return document


def _json_bytes(document: dict | None = None) -> bytes:
    return json.dumps(document or _catalog_document(), ensure_ascii=False).encode("utf-8")


def test_versioned_schema_validation_preserves_extension_data() -> None:
    document = _catalog_document()
    document["catalog"]["x-extension"] = {"unrecognized": ["preserved"]}
    document["catalog"]["groups"][0]["groups"][0]["controls"][0]["x-control-extension"] = True
    content = _json_bytes(document)

    outcome = validate_catalog_bytes(content, CatalogInputFormat.JSON)

    assert outcome.result.valid
    assert outcome.result.validator_name == "compliance-trestle"
    assert outcome.result.validator_version
    assert outcome.result.validation_schema_version is None
    assert outcome.input_format is CatalogInputFormat.JSON
    assert outcome.document == document
    assert outcome.document["catalog"]["uuid"] == document["catalog"]["uuid"]
    assert outcome.document["catalog"]["params"] == document["catalog"]["params"]
    assert (
        outcome.document["catalog"]["metadata"]["props"] == document["catalog"]["metadata"]["props"]
    )
    assert (
        outcome.document["catalog"]["metadata"]["links"] == document["catalog"]["metadata"]["links"]
    )
    assert outcome.document["catalog"]["x-extension"] == {"unrecognized": ["preserved"]}
    assert outcome.result.warnings


def test_yaml_catalog_parsing_preserves_semantics_and_uses_declared_schema() -> None:
    document = _catalog_document()
    content = yaml.safe_dump(document, allow_unicode=True).encode("utf-8")

    outcome = validate_catalog_bytes(content, CatalogInputFormat.YAML)

    assert outcome.result.valid
    assert outcome.input_format is CatalogInputFormat.YAML
    assert outcome.document == document
    assert outcome.document["catalog"]["metadata"]["last-modified"] == "2026-11-09T12:00:00Z"


def test_real_bsi_catalog_validates_as_oscal_1_1_3_without_data_loss() -> None:
    content = BSI_CATALOG_PATH.read_bytes()
    source_document = json.loads(content)

    outcome = validate_catalog_bytes(content)

    assert outcome.result.valid, outcome.result.errors
    assert outcome.result.validator_name == "compliance-trestle"
    assert outcome.result.declared_oscal_version == "1.1.3"
    assert outcome.result.validation_schema_version is None
    assert outcome.document == source_document
    assert outcome.document["catalog"]["metadata"] == source_document["catalog"]["metadata"]
    groups, controls = project_catalog_indexes(outcome.document)
    assert len(groups) == 160
    assert len(controls) == 1000
    assert all(control.group_path is not None for control in controls)
    assert any(group.parent_path is not None for group in groups)


@pytest.mark.parametrize("oscal_version", OSCAL_VERSION_ORDER)
def test_locally_authored_catalog_validates_for_each_supported_version(
    oscal_version: str,
) -> None:
    document = _catalog_document(oscal_version)

    outcome = validate_catalog_bytes(_json_bytes(document))

    assert outcome.result.valid, outcome.result.errors
    assert outcome.result.declared_oscal_version == oscal_version
    if oscal_version in JSON_SCHEMA_OSCAL_VERSIONS:
        assert outcome.result.validator_name == "jsonschema"
        assert outcome.result.validation_schema_version == f"OSCAL {oscal_version}"
    else:
        assert outcome.result.validator_name == "compliance-trestle"
        assert outcome.result.validation_schema_version is None
    assert outcome.document == document


@pytest.mark.parametrize("model", list(OscalDocumentModel))
@pytest.mark.parametrize("oscal_version", JSON_SCHEMA_OSCAL_VERSIONS)
def test_schema_registry_selects_the_official_model_and_version(
    model: OscalDocumentModel, oscal_version: str
) -> None:
    schema = load_oscal_schema(model, oscal_version)

    assert schema["$id"] == (
        f"http://csrc.nist.gov/ns/oscal/{oscal_version}/oscal-{model.value}-schema.json"
    )


def test_official_nist_sp_800_53_catalog_uses_its_declared_1_2_2_schema() -> None:
    content = NIST_CATALOG_PATH.read_bytes()
    source_document = json.loads(content)

    outcome = validate_catalog_bytes(content)

    assert outcome.result.valid, outcome.result.errors
    assert outcome.result.declared_oscal_version == "1.2.2"
    assert outcome.result.validation_schema_version == "OSCAL 1.2.2"
    assert outcome.document == source_document
    _, controls = project_catalog_indexes(outcome.document)
    assert len(controls) == 1196


def test_trestle_model_errors_are_reported_without_document_content() -> None:
    document = _catalog_document()
    document["catalog"]["metadata"]["oscal-version"] = "1.1.3"
    del document["catalog"]["groups"][0]["title"]

    outcome = validate_catalog_bytes(_json_bytes(document))

    assert not outcome.result.valid
    assert outcome.result.validator_name == "compliance-trestle"
    assert outcome.result.errors[0].code == "TRESTLE_MODEL_INVALID"
    assert outcome.result.errors[0].path is not None
    assert outcome.result.errors[0].diagnostic
    assert all("Example Security Catalog" not in error.message for error in outcome.result.errors)


@pytest.mark.parametrize(
    ("content", "expected_format"),
    [
        (_json_bytes(), CatalogInputFormat.JSON),
        (b"\xef\xbb\xbf" + _json_bytes(), CatalogInputFormat.JSON),
        (yaml.safe_dump(_catalog_document()).encode("utf-8"), CatalogInputFormat.YAML),
    ],
)
def test_safe_format_detection(content: bytes, expected_format: CatalogInputFormat) -> None:
    outcome = validate_catalog_bytes(content)

    assert outcome.result.valid
    assert outcome.input_format is expected_format


@pytest.mark.parametrize(
    ("content", "input_format", "expected_code"),
    [
        (b"", "json", "EMPTY_INPUT"),
        (b'{"catalog":', "json", "JSON_SYNTAX_INVALID"),
        (b'{"catalog": {}, "catalog": {}}', "json", "DUPLICATE_OBJECT_KEY"),
        (b"catalog: {}\ncatalog: {}", "yaml", "DUPLICATE_OBJECT_KEY"),
        (b"catalog: [", "yaml", "YAML_SYNTAX_INVALID"),
        (b"catalog: &catalog {uuid: value}\nalias: *catalog", "yaml", "UNSUPPORTED_YAML_FEATURE"),
        (b"catalog: {}\n---\ncatalog: {}", "yaml", "UNSUPPORTED_YAML_FEATURE"),
        (b"!!python/object/apply:os.system ['echo unsafe']", "yaml", "YAML_SYNTAX_INVALID"),
        (b"\xff", "json", "UNSUPPORTED_ENCODING"),
    ],
)
def test_parser_returns_structured_input_errors(
    content: bytes, input_format: str, expected_code: str
) -> None:
    outcome = validate_catalog_bytes(content, input_format)

    assert not outcome.result.valid
    assert outcome.result.errors[0].code == expected_code


def test_size_and_nesting_limits_are_enforced_before_validation() -> None:
    oversized = validate_catalog_bytes(_json_bytes(), max_input_bytes=5)
    deeply_nested = validate_catalog_bytes(b'{"value": [[[[0]]]]}', "json", max_nesting_depth=3)
    yaml_nested = validate_catalog_bytes(
        b"catalog:\n  a:\n    b:\n      c: 1", "yaml", max_nesting_depth=3
    )

    assert oversized.result.errors[0].code == "INPUT_TOO_LARGE"
    assert deeply_nested.result.errors[0].code == "MAX_NESTING_DEPTH"
    assert yaml_nested.result.errors[0].code == "MAX_NESTING_DEPTH"


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda doc: doc.update({"profile": {}}), "UNSUPPORTED_DOCUMENT_TYPE"),
        (lambda doc: doc["catalog"]["metadata"].pop("oscal-version"), "MISSING_OSCAL_VERSION"),
        (
            lambda doc: doc["catalog"]["metadata"].update({"oscal-version": "1.9.0"}),
            "UNSUPPORTED_OSCAL_VERSION",
        ),
        (lambda doc: doc["catalog"].pop("uuid"), "TRESTLE_MODEL_INVALID"),
        (
            lambda doc: doc["catalog"].update({"uuid": "not-a-uuid"}),
            "TRESTLE_MODEL_INVALID",
        ),
        (
            lambda doc: doc["catalog"]["groups"][0]["groups"][0]["controls"][0].pop("title"),
            "TRESTLE_MODEL_INVALID",
        ),
        (
            lambda doc: doc["catalog"]["metadata"].update({"last_modifed": "misspelled"}),
            "TRESTLE_MODEL_INVALID",
        ),
        (
            lambda doc: doc["catalog"].update({"controls": "not-a-control-list"}),
            "TRESTLE_MODEL_INVALID",
        ),
    ],
)
def test_oscal_model_errors_are_specific_and_do_not_include_document_content(
    mutate, expected_code: str
) -> None:
    document = _catalog_document()
    mutate(document)
    outcome = validate_catalog_bytes(_json_bytes(document))

    assert not outcome.result.valid
    assert outcome.result.errors[0].code == expected_code
    assert all("Example Security Catalog" not in error.message for error in outcome.result.errors)


def test_duplicate_control_ids_are_rejected_with_a_document_path() -> None:
    document = _catalog_document()
    document["catalog"]["groups"][0]["groups"][0]["controls"][0]["controls"][0]["id"] = "ac-1"

    outcome = validate_catalog_bytes(_json_bytes(document))

    assert outcome.result.errors[0].code == "DUPLICATE_CONTROL_ID"
    assert outcome.result.errors[0].path == "/catalog/groups/0/groups/0/controls/0/controls/0"


def test_import_validation_failure_exposes_report_without_persisting() -> None:
    outcome = validate_catalog_bytes(_json_bytes())
    assert outcome.result.valid

    bad_document = _catalog_document()
    bad_document["catalog"]["metadata"]["oscal-version"] = "1.9.0"
    service = CatalogImportService(lambda: None)
    with pytest.raises(CatalogImportValidationError) as error:
        service.import_catalog(uuid4(), _json_bytes(bad_document))
    assert error.value.result.errors[0].code == "UNSUPPORTED_OSCAL_VERSION"


@pytest.mark.integration
def test_import_json_yaml_idempotency_updates_and_tenant_isolation(
    grc_service, session_factory
) -> None:
    tenant = grc_service.create_tenant("Import tenant", f"catalog-import-{uuid4().hex}")
    other_tenant = grc_service.create_tenant("Other tenant", f"other-import-{uuid4().hex}")
    service = CatalogImportService(lambda: SQLAlchemyUnitOfWork(session_factory))
    document = _catalog_document()
    publisher_uuid = "0e38e6c1-3a4d-45d7-88b6-6b1a03a4a61a"
    document["catalog"]["metadata"]["roles"] = [{"id": "publisher", "title": "Publisher"}]
    document["catalog"]["metadata"]["parties"] = [
        {"uuid": publisher_uuid, "type": "organization", "name": "OSCAL publisher"}
    ]
    document["catalog"]["metadata"]["responsible-parties"] = [
        {"role-id": "publisher", "party-uuids": [publisher_uuid]}
    ]
    json_result = service.import_catalog(
        tenant.id,
        _json_bytes(document),
        "json",
        CatalogImportMetadata(
            source_uri="https://example.test/catalog.json",
            source_organization="Example publisher",
            license_identifier="CC0-1.0",
        ),
    )

    assert json_result.created
    assert json_result.catalog.name == document["catalog"]["metadata"]["title"]
    assert json_result.revision.oscal_document_uuid.hex == document["catalog"]["uuid"].replace(
        "-", ""
    )
    assert json_result.revision.content_sha256 == canonical_json_sha256(document)
    assert json_result.revision.source_version == "1.0.0"
    assert json_result.revision.source_format == "json"
    assert json_result.control_count == 3
    assert json_result.catalog.source_uri == "https://example.test/catalog.json"
    assert json_result.catalog.source_organization == "Example publisher"
    assert json_result.catalog.license_identifier == "CC0-1.0"

    yaml_result = service.import_catalog(
        tenant.id,
        yaml.safe_dump(document).encode("utf-8"),
        "yaml",
        target_catalog_id=json_result.catalog.id,
    )
    assert not yaml_result.created
    assert yaml_result.revision.id == json_result.revision.id
    assert yaml_result.revision.revision_number == 1

    changed = _catalog_document()
    changed["catalog"]["metadata"]["title"] = "Updated Catalog"
    updated_result = service.import_catalog(
        tenant.id,
        _json_bytes(changed),
        "json",
        target_catalog_id=json_result.catalog.id,
    )
    assert updated_result.created
    assert updated_result.revision.revision_number == 2

    separate_catalog = service.import_catalog(tenant.id, _json_bytes(document), "json")
    assert separate_catalog.created
    assert separate_catalog.catalog.id != json_result.catalog.id
    assert separate_catalog.revision.content_sha256 == json_result.revision.content_sha256
    assert separate_catalog.catalog.source_organization == "OSCAL publisher"

    with pytest.raises(EntityNotFoundError, match="Catalog not found"):
        service.import_catalog(
            other_tenant.id,
            _json_bytes(document),
            "json",
            target_catalog_id=json_result.catalog.id,
        )

    with session_factory() as session:
        stored = session.get(CatalogRevisionRecord, json_result.revision.id)
        assert stored is not None
        assert stored.content == document
        assert stored.oscal_document_uuid.hex == document["catalog"]["uuid"].replace("-", "")
        groups = list(
            session.scalars(
                select(CatalogGroupIndexRecord)
                .where(CatalogGroupIndexRecord.catalog_revision_id == json_result.revision.id)
                .order_by(CatalogGroupIndexRecord.structural_path)
            )
        )
        controls = list(
            session.scalars(
                select(CatalogControlIndexRecord)
                .where(CatalogControlIndexRecord.catalog_revision_id == json_result.revision.id)
                .order_by(CatalogControlIndexRecord.structural_path)
            )
        )
        assert len(groups) == 2
        assert groups[1].parent_group_id == groups[0].id
        assert [control.oscal_control_id for control in controls] == ["ac-1", "ac-1.1", "ac-2"]
        assert controls[1].parent_control_id == controls[0].id
        assert controls[0].group_id == groups[0].id


@pytest.mark.integration
def test_import_real_bsi_catalog_preserves_document_and_relationships(
    grc_service, session_factory
) -> None:
    tenant = grc_service.create_tenant("BSI import", f"bsi-import-{uuid4().hex}")
    content = BSI_CATALOG_PATH.read_bytes()
    document = json.loads(content)
    service = CatalogImportService(lambda: SQLAlchemyUnitOfWork(session_factory))

    imported = service.import_catalog(tenant.id, content)

    assert imported.control_count == 1000
    with session_factory() as session:
        revision = session.get(CatalogRevisionRecord, imported.revision.id)
        assert revision is not None
        assert revision.content == document
        groups = list(
            session.scalars(
                select(CatalogGroupIndexRecord).where(
                    CatalogGroupIndexRecord.catalog_revision_id == imported.revision.id
                )
            )
        )
        controls = list(
            session.scalars(
                select(CatalogControlIndexRecord).where(
                    CatalogControlIndexRecord.catalog_revision_id == imported.revision.id
                )
            )
        )
        assert len(groups) == 160
        assert len(controls) == 1000
        assert any(group.parent_group_id is not None for group in groups)
        assert all(control.group_id is not None for control in controls)


@pytest.mark.integration
def test_import_rollback_removes_new_catalog_on_revision_failure(
    monkeypatch, grc_service, session_factory
) -> None:
    tenant = grc_service.create_tenant("Atomic import", f"atomic-import-{uuid4().hex}")
    service = CatalogImportService(lambda: SQLAlchemyUnitOfWork(session_factory))
    with session_factory() as session:
        before_count = session.scalar(
            select(func.count())
            .select_from(CatalogRecord)
            .where(CatalogRecord.tenant_id == tenant.id)
        )

    def fail_add(self, revision, groups, controls):
        raise RuntimeError("Injected persistence failure")

    monkeypatch.setattr(
        "app.persistence.repositories.SQLCatalogRevisionRepository.add",
        fail_add,
    )
    with pytest.raises(RuntimeError, match="Injected persistence failure"):
        service.import_catalog(tenant.id, _json_bytes())

    with session_factory() as session:
        after_count = session.scalar(
            select(func.count())
            .select_from(CatalogRecord)
            .where(CatalogRecord.tenant_id == tenant.id)
        )
        revisions = session.scalar(
            select(func.count())
            .select_from(CatalogRevisionRecord)
            .where(CatalogRevisionRecord.tenant_id == tenant.id)
        )
    assert after_count == before_count
    assert revisions == 0


@pytest.mark.integration
def test_concurrent_identical_imports_return_one_revision(grc_service, session_factory) -> None:
    tenant = grc_service.create_tenant("Concurrent import", f"concurrent-{uuid4().hex}")
    catalog = grc_service.create_catalog(
        tenant.id,
        "Concurrency target",
        origin_type=CatalogOriginType.IMPORTED,
    )
    content = _json_bytes()

    def import_one():
        return CatalogImportService(lambda: SQLAlchemyUnitOfWork(session_factory)).import_catalog(
            tenant.id, content, "json", target_catalog_id=catalog.id
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _: import_one(), range(2)))

    assert first.revision.id == second.revision.id
    assert sorted([first.created, second.created]) == [False, True]
    with session_factory() as session:
        count = session.scalar(
            select(func.count())
            .select_from(CatalogRevisionRecord)
            .where(CatalogRevisionRecord.catalog_id == catalog.id)
        )
    assert count == 1


@pytest.mark.integration
def test_import_preserves_published_revision_and_creates_updated_draft(
    grc_service, session_factory
) -> None:
    tenant = grc_service.create_tenant("Published import", f"published-{uuid4().hex}")
    service = CatalogImportService(lambda: SQLAlchemyUnitOfWork(session_factory))
    first = service.import_catalog(tenant.id, _json_bytes())
    with session_factory() as session:
        session.execute(
            CatalogRevisionRecord.__table__.update()
            .where(CatalogRevisionRecord.id == first.revision.id)
            .values(lifecycle_status="published", published_at=first.revision.created_at)
        )
        session.commit()

    duplicate = service.import_catalog(
        tenant.id,
        _json_bytes(),
        target_catalog_id=first.catalog.id,
    )
    assert not duplicate.created
    assert duplicate.revision.lifecycle_status is CatalogRevisionStatus.PUBLISHED

    changed = _catalog_document()
    changed["catalog"]["metadata"]["title"] = "Published input changed"
    updated = service.import_catalog(
        tenant.id,
        _json_bytes(changed),
        target_catalog_id=first.catalog.id,
    )
    assert updated.created
    assert updated.revision.revision_number == 2
    with session_factory() as session:
        stored = session.get(CatalogRevisionRecord, first.revision.id)
        assert stored is not None
        assert stored.lifecycle_status == "published"
