# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

import os
import re
import secrets
from pathlib import Path

CREDENTIALS = Path("/run/demo-credentials")
DATABASE = Path("/var/lib/postgresql/data")


def initialize() -> None:
    os.chmod(CREDENTIALS, 0o711)
    password = CREDENTIALS / "postgres-password"
    if not password.exists() and any(DATABASE.iterdir()):
        raise RuntimeError(
            "PostgreSQL data exists but its credential is missing; restore the credential volume."
        )

    for path, group in ((password, 10002), (CREDENTIALS / "demo-auth-secret", 10001)):
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
            with os.fdopen(fd, "w", encoding="ascii") as output:
                output.write(secrets.token_hex(32))
                output.flush()
                os.fsync(output.fileno())
        if not re.fullmatch(r"[0-9a-f]{64}", path.read_text(encoding="ascii")):
            raise RuntimeError(f"Invalid credential file: {path.name}")
        os.chown(path, 0, group)
        os.chmod(path, 0o440)


if __name__ == "__main__":
    initialize()
