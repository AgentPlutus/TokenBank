"""FastAPI dependency helpers."""

from __future__ import annotations

import sqlite3

from fastapi import Request

from tokenbank.app.security import AuthContext, TokenKind, require_token_kind
from tokenbank.config_runtime.loader import LoadedConfig


def get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def get_loaded_config(request: Request) -> LoadedConfig:
    return request.app.state.loaded_config


def require_host_token(request: Request) -> AuthContext:
    return require_token_kind(request, TokenKind.HOST)


def require_worker_token(request: Request) -> AuthContext:
    return require_token_kind(request, TokenKind.WORKER)


def require_internal_token(request: Request) -> AuthContext:
    return require_token_kind(request, TokenKind.INTERNAL)

