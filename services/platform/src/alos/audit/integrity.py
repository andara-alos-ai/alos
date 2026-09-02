import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True, slots=True)
class AuditChainIssue:
    audit_entry_id: UUID
    reason: str


@dataclass(frozen=True, slots=True)
class AuditChainReport:
    checked_entries: int
    checked_organizations: int
    issues: tuple[AuditChainIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


def compute_audit_entry_hash(
    *,
    organization_id: UUID,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    correlation_id: UUID,
    reason: str | None,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    occurred_at: datetime,
    previous_hash: str | None,
) -> str:
    canonical = json.dumps(
        {
            "organization_id": str(organization_id),
            "actor_id": actor_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "correlation_id": str(correlation_id),
            "reason": reason,
            "before": before,
            "after": after,
            "occurred_at": occurred_at.isoformat(),
            "previous_hash": previous_hash,
        },
        default=str,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def verify_audit_chains(database_url: str) -> AuditChainReport:
    issues: list[AuditChainIssue] = []
    organizations: set[UUID] = set()
    connection_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(connection_url, row_factory=dict_row) as connection:
        legacy_exceptions = {
            (row["organization_id"], row["audit_entry_id"])
            for row in connection.execute(
                "SELECT organization_id, audit_entry_id "
                "FROM audit.chain_legacy_exceptions"
            ).fetchall()
        }
        rows = connection.execute(
            """
            SELECT audit_entry_id, organization_id, occurred_at, actor_id, action,
                   entity_type, entity_id, reason, before_masked, after_masked,
                   correlation_id, previous_hash, entry_hash
            FROM audit.entries
            ORDER BY organization_id NULLS FIRST, occurred_at, audit_entry_id
            """
        ).fetchall()
    hashes_by_organization: dict[UUID, dict[str, Mapping[str, Any]]] = {}
    children_by_predecessor: dict[tuple[UUID, str], list[UUID]] = {}
    for row in rows:
        audit_entry_id = row["audit_entry_id"]
        organization_id = row["organization_id"]
        if organization_id is None:
            issues.append(
                AuditChainIssue(audit_entry_id, "organization_id audit tidak tersedia")
            )
            continue
        organizations.add(organization_id)
        stored_previous = row["previous_hash"]
        expected_hash = compute_audit_entry_hash(
            organization_id=organization_id,
            actor_id=row["actor_id"],
            action=row["action"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            correlation_id=row["correlation_id"],
            reason=row["reason"],
            before=row["before_masked"],
            after=row["after_masked"],
            occurred_at=row["occurred_at"],
            previous_hash=stored_previous,
        )
        if row["entry_hash"] != expected_hash:
            issues.append(AuditChainIssue(audit_entry_id, "entry_hash tidak valid"))
        organization_hashes = hashes_by_organization.setdefault(organization_id, {})
        if row["entry_hash"] in organization_hashes:
            issues.append(AuditChainIssue(audit_entry_id, "entry_hash duplikat"))
        organization_hashes[row["entry_hash"]] = row
        if stored_previous is not None:
            children_by_predecessor.setdefault(
                (organization_id, stored_previous), []
            ).append(audit_entry_id)

    for organization_id, organization_hashes in hashes_by_organization.items():
        for entry in organization_hashes.values():
            audit_entry_id = entry["audit_entry_id"]
            previous_hash = entry["previous_hash"]
            if previous_hash is None:
                continue
            predecessor = organization_hashes.get(previous_hash)
            if predecessor is None:
                if (organization_id, audit_entry_id) not in legacy_exceptions:
                    issues.append(
                        AuditChainIssue(
                            audit_entry_id,
                            "predecessor tidak tersedia dan entri bukan pengecualian historis",
                        )
                    )
                continue
            if predecessor["occurred_at"] > entry["occurred_at"]:
                issues.append(
                    AuditChainIssue(audit_entry_id, "predecessor terjadi setelah entri")
                )

        for (
            fork_organization_id,
            _previous_hash,
        ), child_ids in children_by_predecessor.items():
            if fork_organization_id != organization_id or len(child_ids) <= 1:
                continue
            for child_id in child_ids:
                if (organization_id, child_id) not in legacy_exceptions:
                    issues.append(AuditChainIssue(child_id, "fork audit chain tidak diizinkan"))

        for entry in organization_hashes.values():
            seen: set[str] = set()
            current = entry
            while current["previous_hash"] in organization_hashes:
                current_hash = current["entry_hash"]
                if current_hash in seen:
                    issues.append(
                        AuditChainIssue(entry["audit_entry_id"], "siklus audit chain terdeteksi")
                    )
                    break
                seen.add(current_hash)
                current = organization_hashes[current["previous_hash"]]
    return AuditChainReport(
        checked_entries=len(rows),
        checked_organizations=len(organizations),
        issues=tuple(issues),
    )
