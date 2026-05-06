"""Token-prefix auth helpers for WP4 endpoint skeletons."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from fastapi import HTTPException, Request, status


class TokenKind(StrEnum):
    HOST = "host"
    WORKER = "worker"
    INTERNAL = "internal"


TOKEN_PREFIXES = {
    TokenKind.HOST: "tbk_h_",
    TokenKind.WORKER: "tbk_w_",
    TokenKind.INTERNAL: "tbk_i_",
}


@dataclass(frozen=True)
class AuthContext:
    token_kind: TokenKind
    token_prefix: str


def _extract_bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_bearer_token"},
        )
    return token


def require_token_kind(request: Request, token_kind: TokenKind) -> AuthContext:
    token = _extract_bearer_token(request)
    required_prefix = TOKEN_PREFIXES[token_kind]
    if not token.startswith(required_prefix):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "wrong_token_kind"},
        )
    return AuthContext(
        token_kind=token_kind,
        token_prefix=token[: min(len(token), len(required_prefix) + 8)],
    )

