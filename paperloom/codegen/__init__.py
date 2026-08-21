"""Selects the codegen backend for a project's target language (spec §2.2a)."""
from .pyside_backend import PySideBackend
from .cpp_backend import CppBackend
from ..components.registry import ComponentRegistry

_BACKENDS = {
    "pyside6": PySideBackend,
    "cpp": CppBackend,
}


def get_backend(target: str, registry: ComponentRegistry):
    backend_cls = _BACKENDS.get(target)
    if backend_cls is None:
        raise ValueError(f"No codegen backend for target '{target}' (available: {list(_BACKENDS)})")
    return backend_cls(registry)
