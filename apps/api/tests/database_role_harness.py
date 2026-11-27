# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""Separate-role PostgreSQL harness support (ADR 0029 acceptance-test prerequisites).

One dedicated ``_test`` database is reached through three credentials. The owner
migrates, prepares fixtures and cleans up; business tests use the runtime engine; the
provisioner engine is reserved for provisioning tests. Every engine verifies its effective
role on each new connection, so a business engine cannot silently use owner credentials.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from sqlalchemy import Connection, Engine
from sqlalchemy.engine import make_url

from app.persistence.database_roles import OWNER_ROLE, PROVISIONER_ROLE, RUNTIME_ROLE

ROLE_URL_VARIABLES = {
    OWNER_ROLE: "TEST_DATABASE_OWNER_URL",
    RUNTIME_ROLE: "TEST_DATABASE_RUNTIME_URL",
    PROVISIONER_ROLE: "TEST_DATABASE_PROVISIONER_URL",
}
REQUIRE_OPTION = "--require-database-roles"
MISSING_CONFIGURATION = (
    "Set TEST_DATABASE_OWNER_URL, TEST_DATABASE_RUNTIME_URL and "
    "TEST_DATABASE_PROVISIONER_URL to run separate-role PostgreSQL tests."
)


class RoleHarnessConfigurationError(ValueError):
    pass


def load_role_urls() -> dict[str, str] | None:
    """Return validated role URLs, ``None`` if none are set; reject partial configuration."""
    urls = {role: os.environ.get(variable, "") for role, variable in ROLE_URL_VARIABLES.items()}
    present = {role: url for role, url in urls.items() if url}
    if not present:
        return None
    if len(present) != len(urls):
        missing = [ROLE_URL_VARIABLES[role] for role, url in urls.items() if not url]
        raise RoleHarnessConfigurationError(f"Incomplete role configuration; missing {missing}.")
    locations = set()
    passwords = set()
    for role, url in present.items():
        parsed = make_url(url)
        if parsed.get_backend_name() != "postgresql":
            raise RoleHarnessConfigurationError(f"{ROLE_URL_VARIABLES[role]} must use PostgreSQL.")
        if not parsed.database or not parsed.database.endswith("_test"):
            raise RoleHarnessConfigurationError(
                f"{ROLE_URL_VARIABLES[role]} must target a database whose name ends in '_test'."
            )
        if parsed.username != role:
            raise RoleHarnessConfigurationError(
                f"{ROLE_URL_VARIABLES[role]} must authenticate as {role!r}."
            )
        if not parsed.password:
            raise RoleHarnessConfigurationError(f"{ROLE_URL_VARIABLES[role]} must set a password.")
        locations.add((parsed.host, parsed.port, parsed.database))
        passwords.add(parsed.password)
    if len(locations) != 1:
        raise RoleHarnessConfigurationError("All role URLs must target the same _test database.")
    if len(passwords) != len(present):
        raise RoleHarnessConfigurationError("Each role URL must use a distinct password.")
    return present


def same_database(first_url: str, second_url: str) -> bool:
    first, second = make_url(first_url), make_url(second_url)
    return (first.host, first.port, first.database) == (second.host, second.port, second.database)


@dataclass
class OwnerCleanup:
    """Owner-controlled cleanup that runs every registered action, even after failures."""

    engine: Engine
    _actions: list[tuple[str, Callable[[Connection], None]]] = field(default_factory=list)

    def add(self, description: str, action: Callable[[Connection], None]) -> None:
        self._actions.append((description, action))

    def run(self) -> list[str]:
        failures: list[str] = []
        while self._actions:
            description, action = self._actions.pop()
            try:
                with self.engine.begin() as connection:
                    action(connection)
            except Exception as error:  # noqa: BLE001 - collect all cleanup failures
                failures.append(f"{description}: {type(error).__name__}: {error}")
        return failures


def run_synchronized[T](
    *workers: Callable[[threading.Barrier], T], timeout_seconds: float = 10.0
) -> list[T]:
    """Run workers in separate threads that rendezvous on a bounded barrier.

    Each worker owns its own connection and transaction. Workers must bound database waits
    (for example with ``SET LOCAL lock_timeout``); this helper bounds result collection and
    never waits for hung threads on exit.
    """
    barrier = threading.Barrier(len(workers), timeout=timeout_seconds)
    executor = ThreadPoolExecutor(max_workers=len(workers))
    try:
        futures = [executor.submit(worker, barrier) for worker in workers]
        return [future.result(timeout=timeout_seconds) for future in futures]
    finally:
        barrier.abort()
        executor.shutdown(wait=False, cancel_futures=True)
