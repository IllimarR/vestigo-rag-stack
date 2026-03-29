"""Admin API route definitions.

Kept separate from `services/admin/api.py` so the FastAPI factory stays
slim and the route bodies are individually testable. Three groupings:

  * `/v1/config/*` — model, chunking, prompt template, default
    collection. Whole-section reads and writes, no inner-field edits.
    Writes emit `admin_event` audit entries.
  * `/v1/audit` — read-only audit log query with the same filter
    vocabulary `AuditLogger.query_logs` already supports.
  * `/v1/api-keys/*` — list / create / revoke. The plaintext is
    returned exactly once on create — there is no read path that
    surfaces it later.

Auth is intentionally minimal: a shared `ADMIN_API_KEY` env value. The
admin UI proxies through this; per-user / role-aware auth is a Phase 6
follow-up that doesn't change the route shape.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from contracts import (
    AuditLogger,
    ChunkConfig,
    ConfigProvider,
    EmbeddingConfig,
    GenerationConfig,
    RerankerConfig,
)
from fastapi import APIRouter, Header, HTTPException, Query, Request

from services.admin.application.api_key_store import ApiKeyStore, EnvApiKeyStore

__all__ = ["ADMIN_ACTOR", "build_router", "verify_admin_auth"]

ADMIN_ACTOR = "admin"
_BEARER_PREFIX = "Bearer "


def verify_admin_auth(authorization: str | None) -> None:
    """Single-tenant bearer check.

    `ADMIN_API_KEY` env unset → admin runs unauthenticated (dev mode).
    Sets the composition-root warning analogous to the gateway's.
    Production deployments must set the env value.
    """

    expected = os.getenv("ADMIN_API_KEY", "").strip()
    if not expected:
        return
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="missing Authorization: Bearer <admin-key>")
    candidate = authorization[len(_BEARER_PREFIX) :].strip()
    if candidate != expected:
        raise HTTPException(status_code=401, detail="admin key not recognised")


def _config_provider(request: Request) -> ConfigProvider:
    return request.app.state.config_provider  # type: ignore[no-any-return]


def _audit_logger(request: Request) -> AuditLogger:
    return request.app.state.audit_logger  # type: ignore[no-any-return]


def _api_key_store(request: Request) -> ApiKeyStore:
    return request.app.state.api_key_store  # type: ignore[no-any-return]


def _now() -> datetime:
    return datetime.now(UTC)


def _audit_admin(request: Request, action: str) -> None:
    _audit_logger(request).log_admin_event(
        action=action, actor=ADMIN_ACTOR, timestamp=_now()
    )


def _validate_or_400(model: type[Any], body: dict[str, Any]) -> Any:
    try:
        return model(**body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _build_config_router() -> APIRouter:
    router = APIRouter(prefix="/v1/config")

    @router.get("")
    def get_config(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        verify_admin_auth(authorization)
        cp = _config_provider(request)
        return {
            "embedding": cp.get_embedding_config().model_dump(mode="json"),
            "reranker": cp.get_reranker_config().model_dump(mode="json"),
            "generation": cp.get_generation_config().model_dump(mode="json"),
            "chunking": cp.get_chunking_config().model_dump(mode="json"),
            "rag_prompt_template": cp.get_rag_prompt_template(),
            "default_collection": cp.get_default_collection(),
        }

    @router.put("/embedding")
    async def set_embedding(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        verify_admin_auth(authorization)
        body = await request.json()
        config: EmbeddingConfig = _validate_or_400(EmbeddingConfig, body)
        _config_provider(request).set_embedding_config(config)
        _audit_admin(request, "config.embedding.set")
        return {"status": "ok"}

    @router.put("/reranker")
    async def set_reranker(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        verify_admin_auth(authorization)
        body = await request.json()
        config: RerankerConfig = _validate_or_400(RerankerConfig, body)
        _config_provider(request).set_reranker_config(config)
        _audit_admin(request, "config.reranker.set")
        return {"status": "ok"}

    @router.put("/generation")
    async def set_generation(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        verify_admin_auth(authorization)
        body = await request.json()
        config: GenerationConfig = _validate_or_400(GenerationConfig, body)
        _config_provider(request).set_generation_config(config)
        _audit_admin(request, "config.generation.set")
        return {"status": "ok"}

    @router.put("/chunking")
    async def set_chunking(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        verify_admin_auth(authorization)
        body = await request.json()
        config: ChunkConfig = _validate_or_400(ChunkConfig, body)
        _config_provider(request).set_chunking_config(config)
        _audit_admin(request, "config.chunking.set")
        return {"status": "ok"}

    @router.put("/rag-prompt-template")
    async def set_prompt_template(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        verify_admin_auth(authorization)
        body = await request.json()
        template = body.get("template") if isinstance(body, dict) else None
        if not isinstance(template, str):
            raise HTTPException(status_code=400, detail="body must be {'template': str}")
        _config_provider(request).set_rag_prompt_template(template)
        _audit_admin(request, "config.rag_prompt_template.set")
        return {"status": "ok"}

    @router.put("/default-collection")
    async def set_default_collection(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        verify_admin_auth(authorization)
        body = await request.json()
        collection = body.get("collection") if isinstance(body, dict) else None
        if not isinstance(collection, str) or not collection:
            raise HTTPException(
                status_code=400, detail="body must be {'collection': non-empty-str}"
            )
        _config_provider(request).set_default_collection(collection)
        _audit_admin(request, "config.default_collection.set")
        return {"status": "ok"}

    return router


def _build_audit_router() -> APIRouter:
    router = APIRouter(prefix="/v1")

    @router.get("/audit")
    def get_audit(
        request: Request,
        authorization: str | None = Header(default=None),
        type_: str | None = Query(default=None, alias="type"),
        api_key_id: str | None = Query(default=None),
        status: str | None = Query(default=None),
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        verify_admin_auth(authorization)
        filters: dict[str, Any] = {}
        if type_:
            filters["type"] = type_
        if api_key_id:
            filters["api_key_id"] = api_key_id
        if status:
            filters["status"] = status
        if date_from:
            filters["date_from"] = date_from
        if date_to:
            filters["date_to"] = date_to
        rows = _audit_logger(request).query_logs(filters=filters, offset=offset, limit=limit)
        return {"results": rows, "offset": offset, "limit": limit}

    return router


def _build_api_keys_router() -> APIRouter:
    router = APIRouter(prefix="/v1/api-keys")

    @router.get("")
    def list_keys(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        verify_admin_auth(authorization)
        records = _api_key_store(request).list_keys()
        return {
            "results": [
                {
                    "audit_id": r.audit_id,
                    "name": r.name,
                    "created_at": r.created_at.isoformat(),
                    "revoked": r.revoked,
                }
                for r in records
            ]
        }

    @router.post("")
    async def create_key(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        verify_admin_auth(authorization)
        body = await request.json()
        name = body.get("name") if isinstance(body, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise HTTPException(status_code=400, detail="body must be {'name': non-empty-str}")
        store = _api_key_store(request)
        if isinstance(store, EnvApiKeyStore):
            raise HTTPException(
                status_code=409,
                detail="API_KEY_BACKEND=env is read-only; switch to sqlite to manage keys.",
            )
        created = store.create_key(name=name.strip())
        _audit_admin(request, f"api_key.create:{created.record.audit_id}")
        return {
            "plaintext": created.plaintext,
            "audit_id": created.record.audit_id,
            "name": created.record.name,
            "created_at": created.record.created_at.isoformat(),
        }

    @router.delete("/{audit_id}")
    def revoke_key(
        audit_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        verify_admin_auth(authorization)
        store = _api_key_store(request)
        if isinstance(store, EnvApiKeyStore):
            raise HTTPException(
                status_code=409,
                detail="API_KEY_BACKEND=env is read-only; switch to sqlite to revoke keys.",
            )
        changed = store.revoke_key(audit_id)
        if not changed:
            raise HTTPException(status_code=404, detail="key not found or already revoked")
        _audit_admin(request, f"api_key.revoke:{audit_id}")
        return {"status": "revoked"}

    return router


def build_router() -> APIRouter:
    """Aggregate all admin routes into one router for `create_app`."""

    router = APIRouter()
    router.include_router(_build_config_router())
    router.include_router(_build_audit_router())
    router.include_router(_build_api_keys_router())
    return router
