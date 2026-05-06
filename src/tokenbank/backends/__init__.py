"""Backend registry, resolution, and adapter helpers."""

from tokenbank.backends.adapter import (
    BackendExecutionContext,
    UnsupportedBackendAdapter,
    adapter_for_backend_class,
)
from tokenbank.backends.registry import BackendRegistry, BackendRegistryRepository
from tokenbank.backends.resolver import BackendResolution, BackendResolver

__all__ = [
    "BackendExecutionContext",
    "BackendRegistry",
    "BackendRegistryRepository",
    "BackendResolution",
    "BackendResolver",
    "UnsupportedBackendAdapter",
    "adapter_for_backend_class",
]
