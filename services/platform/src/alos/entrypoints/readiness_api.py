"""Human-owned H5 release-readiness decisions; GENESIS cannot call this boundary."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.config import get_settings
from alos.identity import HumanRole
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext, get_current_actor

router = APIRouter(prefix="/api/v1/readiness", tags=["h5-readiness"])


class ReleaseDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID | None = None
    decision: Literal["PENDING", "GO", "HOLD", "NO_GO"] = "PENDING"
    commit_sha: str = Field(min_length=7, max_length=128)
    release_version: str = Field(min_length=1, max_length=160)
    technical_readiness: Literal["PASS", "HOLD", "BLOCKED", "FAIL"]
    uat_report_reference: str | None = Field(default=None, max_length=500)
    restore_evidence_reference: str | None = Field(default=None, max_length=500)
    known_limitations: list[str] = Field(default_factory=list, max_length=100)
    hardening_backlog: list[str] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=10_000)


class ReleaseDecisionRecord(ReleaseDecisionRequest):
    decision_id: UUID
    decided_by_user_id: UUID | None
    decided_at: datetime | None
    created_at: datetime


@router.post(
    "/decisions", response_model=ReleaseDecisionRecord, status_code=status.HTTP_201_CREATED
)
def record_release_decision(
    request: ReleaseDecisionRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> ReleaseDecisionRecord:
    """A Director records the human decision; PENDING is the safe initial state."""

    if HumanRole.DIRECTOR not in actor.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Director authority required"
        )
    if request.workspace_id is not None and request.workspace_id not in actor.workspace_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="workspace access denied")
    now = datetime.now(UTC) if request.decision != "PENDING" else None
    database_url = psycopg_url(get_settings().database_url)
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            INSERT INTO compliance.release_decisions (
                organization_id, workspace_id, decision, decided_by_user_id, decided_at,
                commit_sha, release_version, technical_readiness, uat_report_reference,
                restore_evidence_reference, known_limitations, hardening_backlog, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING decision_id, organization_id, workspace_id, decision, decided_by_user_id,
                      decided_at, commit_sha, release_version, technical_readiness,
                      uat_report_reference, restore_evidence_reference, known_limitations,
                      hardening_backlog, notes, created_at
            """,
            (
                actor.organization_id,
                request.workspace_id,
                request.decision,
                actor.user_id if now else None,
                now,
                request.commit_sha,
                request.release_version,
                request.technical_readiness,
                request.uat_report_reference,
                request.restore_evidence_reference,
                Jsonb(request.known_limitations),
                Jsonb(request.hardening_backlog),
                request.notes,
            ),
        ).fetchone()
        connection.commit()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="decision was not stored"
        )
    return ReleaseDecisionRecord(**row)


@router.get("/decisions", response_model=list[ReleaseDecisionRecord])
def list_release_decisions(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> list[ReleaseDecisionRecord]:
    if HumanRole.DIRECTOR not in actor.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Director authority required"
        )
    with psycopg.connect(
        psycopg_url(get_settings().database_url), row_factory=dict_row
    ) as connection:
        rows = connection.execute(
            """
            SELECT decision_id, workspace_id, decision, decided_by_user_id, decided_at,
                   commit_sha, release_version, technical_readiness, uat_report_reference,
                   restore_evidence_reference, known_limitations, hardening_backlog,
                   notes, created_at
            FROM compliance.release_decisions
            WHERE organization_id = %s
            ORDER BY created_at DESC
            """,
            (actor.organization_id,),
        ).fetchall()
    return [ReleaseDecisionRecord(**row) for row in rows]
