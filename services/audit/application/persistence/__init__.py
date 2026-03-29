"""SQLAlchemy models owned by the audit service.

Importing this module registers the audit tables on
`control_plane.Base.metadata`.
"""

from __future__ import annotations

from services.audit.application.persistence.models import AuditEvent

__all__ = ["AuditEvent"]
