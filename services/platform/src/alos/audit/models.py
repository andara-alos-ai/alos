from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

AuditActorKind = Literal["HUMAN", "SYSTEM"]


class AuditEvent(BaseModel):
    actor_kind: AuditActorKind
    action: str = Field(min_length=3, max_length=120)
    entity_type: str = Field(min_length=3, max_length=120)
    entity_id: UUID | None = None
    correlation_id: UUID
    reason: str = Field(min_length=3, max_length=1000)
    occurred_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
