"""Token hashing helpers shared across control-plane and worker code."""

from __future__ import annotations

import hashlib


def assignment_lease_token_hash(raw_token: str) -> str:
    """Return the stable hash for an assignment lease token."""
    digest = hashlib.sha256()
    digest.update(b"tokenbank.assignment.lease.v1\0")
    digest.update(raw_token.encode("utf-8"))
    return digest.hexdigest()

