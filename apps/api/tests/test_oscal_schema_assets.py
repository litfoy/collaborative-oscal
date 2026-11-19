# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import hashlib

import pytest
from collaborative_oscal_oscal.versions import OscalDocumentModel, schema_resource

SCHEMA_SHA256 = {
    OscalDocumentModel.ASSESSMENT_PLAN: (
        "0153e4e0414903c51c13732d4158d955630e33a3ef009d2691cf3e07336136f4"
    ),
    OscalDocumentModel.CATALOG: "c0ae626d6bafe318db68692152d0cbbebf29ba7226b1596a5513cc5d1754504d",
    OscalDocumentModel.PROFILE: "3b92e83ef9043af573ca81a451f899adf6855440b0974fb448b9c635fead7983",
    OscalDocumentModel.MAPPING: "5b8f6f9b8117bb42ad8466d11d1695f0be9cc31350c2a3aea770614d96d70d3f",
    OscalDocumentModel.COMPONENT_DEFINITION: (
        "ce95b3b3ea8de87c020ad4a91075241f6f863a77afe212ee828009830d6042d1"
    ),
    OscalDocumentModel.SYSTEM_SECURITY_PLAN: (
        "3027ffb23ba94a8ca4e43ce9417cf2b02f27b7c36d8a4ead8fe2905483c6d10a"
    ),
}


@pytest.mark.parametrize(("model", "expected_digest"), SCHEMA_SHA256.items())
def test_official_oscal_121_schema_digest(
    model: OscalDocumentModel, expected_digest: str
) -> None:
    schema = schema_resource(model, "1.2.1").read_bytes()

    assert hashlib.sha256(schema).hexdigest() == expected_digest
