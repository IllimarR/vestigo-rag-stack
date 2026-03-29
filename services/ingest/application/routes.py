"""Ingest API route definitions.

Two endpoints under `/v1/`:

  * `POST /v1/documents` — single-document push. The route stages the
    payload on the `ApiPushSourceConnector`, drains the resulting event,
    feeds it to the `IngestPipelineOrchestrator`, and returns the
    per-document result. Memory is released via `connector.drop(...)`
    on success and failure both — no accumulation between calls.
  * `POST /v1/documents/batch` — same but with an array of payloads in
    one request. Useful for bulk ingestion clients; the server still
    applies events sequentially through the orchestrator.

A push is only valid when the connector backend is the API push variant
(`SOURCE_CONNECTORS=api`). Other backends raise 409 — fail loud rather
than silently swallow uploads.

Auth is a shared `INGEST_API_KEY` env value, same pattern as the Admin
API. Empty env = dev-mode unauthenticated; the composition root logs a
warning so this isn't a silent dev-mode-in-production trap.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime
from typing import Any

from contracts import (
    ChangeEvent,
    ChangeType,
    ConfigProvider,
)
from fastapi import APIRouter, Header, HTTPException, Request

from services.ingest.application.api_push_source_connector import (
    ApiPushSourceConnector,
)
from services.ingest.application.ingest_pipeline_orchestrator import (
    IngestPipelineOrchestrator,
    IngestResult,
)

__all__ = ["build_router", "verify_ingest_auth"]

_BEARER_PREFIX = "Bearer "


def verify_ingest_auth(authorization: str | None) -> None:
    expected = os.getenv("INGEST_API_KEY", "").strip()
    if not expected:
        return
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        raise HTTPException(
            status_code=401, detail="missing Authorization: Bearer <ingest-key>"
        )
    candidate = authorization[len(_BEARER_PREFIX) :].strip()
    if candidate != expected:
        raise HTTPException(status_code=401, detail="ingest key not recognised")


def _connector(request: Request) -> ApiPushSourceConnector:
    connector = request.app.state.source_connector
    if not isinstance(connector, ApiPushSourceConnector):
        raise HTTPException(
            status_code=409,
            detail=(
                "Ingest push routes require SOURCE_CONNECTORS=api. "
                f"Current backend: {type(connector).__name__}."
            ),
        )
    return connector


def _orchestrator(request: Request) -> IngestPipelineOrchestrator:
    return request.app.state.ingest_orchestrator  # type: ignore[no-any-return]


def _config_provider(request: Request) -> ConfigProvider:
    return request.app.state.config_provider  # type: ignore[no-any-return]


def _resolve_collection(request: Request, override: str | None) -> str:
    if override:
        return override
    return _config_provider(request).get_default_collection()


def _parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"last_modified must be ISO-8601, got {value!r}"
            ) from exc
    raise HTTPException(
        status_code=400, detail="last_modified must be an ISO-8601 string or omitted"
    )


def _stage_event(connector: ApiPushSourceConnector, doc: dict[str, Any]) -> ChangeEvent:
    document_id = doc.get("document_id")
    if not isinstance(document_id, str) or not document_id.strip():
        raise HTTPException(
            status_code=400, detail="document_id must be a non-empty string"
        )

    raw_change_type = (doc.get("change_type") or "added").lower()
    if raw_change_type not in {"added", "modified", "deleted"}:
        raise HTTPException(
            status_code=400,
            detail=f"change_type must be one of added/modified/deleted; got {raw_change_type!r}",
        )

    last_modified = _parse_iso(doc.get("last_modified"))

    if raw_change_type == "deleted":
        return connector.push_deletion(
            document_id=document_id,
            filename=doc.get("filename"),
            last_modified=last_modified,
        )

    filename = doc.get("filename")
    file_type = doc.get("file_type")
    content_b64 = doc.get("content_base64")
    if not isinstance(filename, str) or not filename:
        raise HTTPException(status_code=400, detail="filename is required for added/modified")
    if not isinstance(file_type, str) or not file_type:
        raise HTTPException(status_code=400, detail="file_type is required for added/modified")
    if not isinstance(content_b64, str) or not content_b64:
        raise HTTPException(
            status_code=400, detail="content_base64 is required for added/modified"
        )
    try:
        content = base64.b64decode(content_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"content_base64 not valid: {exc}") from exc

    metadata = doc.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="metadata must be an object")
    source_url = doc.get("source_url")
    if source_url is not None and not isinstance(source_url, str):
        raise HTTPException(status_code=400, detail="source_url must be a string or null")

    event = connector.push_document(
        document_id=document_id,
        filename=filename,
        file_type=file_type,
        content=content,
        last_modified=last_modified,
        metadata=metadata,
        source_url=source_url,
    )
    # The connector decided ADDED vs MODIFIED based on prior state. If the
    # caller explicitly said "modified", trust their declaration over the
    # connector's bookkeeping — useful when the connector is restarted mid-life
    # but the operator knows this is an update.
    if raw_change_type == "modified" and event.change_type is not ChangeType.MODIFIED:
        return ChangeEvent(reference=event.reference, change_type=ChangeType.MODIFIED)
    return event


def _result_label(event: ChangeEvent, result: IngestResult) -> str:
    """Map a single-document orchestrator run back to one of the per-event
    result labels the client expects."""

    if result.failed:
        return "failed"
    if result.skipped:
        return "skipped"
    if event.change_type is ChangeType.DELETED:
        return "deleted"
    if event.change_type is ChangeType.MODIFIED:
        return "updated"
    return "ingested"


def build_router() -> APIRouter:
    router = APIRouter(prefix="/v1")

    @router.post("/documents")
    async def push_document(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        verify_ingest_auth(authorization)
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")

        connector = _connector(request)
        orchestrator = _orchestrator(request)
        collection = _resolve_collection(request, body.get("collection"))

        event = _stage_event(connector, body)
        try:
            result = orchestrator.process_changes([event], collection=collection)
        finally:
            connector.drop(event.reference.document_id)

        return {
            "document_id": event.reference.document_id,
            "change_type": event.change_type.value,
            "result": _result_label(event, result),
            "ingested": result.ingested,
            "updated": result.updated,
            "deleted": result.deleted,
            "skipped": result.skipped,
            "failed": result.failed,
            "collection": collection,
        }

    @router.post("/documents/batch")
    async def push_documents_batch(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        verify_ingest_auth(authorization)
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        docs = body.get("documents")
        if not isinstance(docs, list) or not docs:
            raise HTTPException(
                status_code=400, detail="documents must be a non-empty list of objects"
            )

        connector = _connector(request)
        orchestrator = _orchestrator(request)
        collection = _resolve_collection(request, body.get("collection"))

        events = [_stage_event(connector, doc) for doc in docs]
        try:
            result = orchestrator.process_changes(events, collection=collection)
        finally:
            for event in events:
                connector.drop(event.reference.document_id)

        return {
            "collection": collection,
            "ingested": result.ingested,
            "updated": result.updated,
            "deleted": result.deleted,
            "skipped": result.skipped,
            "failed": result.failed,
            "documents": [
                {
                    "document_id": event.reference.document_id,
                    "change_type": event.change_type.value,
                }
                for event in events
            ],
        }

    return router
