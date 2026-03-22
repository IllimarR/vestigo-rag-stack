"""Top-level namespace for service modules.

Each immediate subpackage is one of the seven modules described in
`docs/architecture.md`. Services expose their public surface via `api.py`;
all of `application/`, `domain/`, and `infrastructure/` are private and must
not be imported across service boundaries — only `contracts` is.
"""
