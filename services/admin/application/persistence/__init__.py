"""SQLAlchemy models owned by the admin service.

Importing this module registers the admin tables on the shared
`control_plane.Base.metadata`, so a single `Base.metadata.create_all`
in the composition root materialises both admin and audit schemas.
"""

from __future__ import annotations

from services.admin.application.persistence.models import ConfigEntry

__all__ = ["ConfigEntry"]
