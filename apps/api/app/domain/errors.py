# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

class EntityNotFoundError(LookupError):
    """Raised when an entity is absent from the requested tenant scope."""


class DomainInvariantError(ValueError):
    """Raised when a requested change violates a domain invariant."""
