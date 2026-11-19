# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Tenant:
    id: UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
