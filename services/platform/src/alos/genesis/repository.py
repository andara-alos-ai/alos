import json
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from alos.agents.contract import AgentDefinition
from alos.genesis.models import (
    GenesisLifecycleStatus,
    GenesisPipelineView,
    GenesisReleaseView,
    GenesisReviewCreate,
    GenesisReviewView,
)


class GenesisStore(Protocol):
    def create(self, view: GenesisPipelineView) -> GenesisPipelineView: ...

    def get(self, request_id: UUID, organization_id: UUID) -> GenesisPipelineView: ...

    def add_review(
        self,
        request_id: UUID,
        organization_id: UUID,
        reviewer_user_id: UUID,
        command: GenesisReviewCreate,
    ) -> GenesisPipelineView: ...

    def stage(
        self,
        request_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
        contract: AgentDefinition,
    ) -> GenesisPipelineView: ...

    def release(
        self,
        request_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> GenesisPipelineView: ...


class InMemoryGenesisStore:
    def __init__(self) -> None:
        self._records: dict[tuple[UUID, UUID], GenesisPipelineView] = {}

    def create(self, view: GenesisPipelineView) -> GenesisPipelineView:
        key = (view.organization_id, view.request_id)
        if key in self._records:
            raise ValueError("Genesis request sudah ada")
        self._records[key] = view
        return view

    def get(self, request_id: UUID, organization_id: UUID) -> GenesisPipelineView:
        try:
            return self._records[(organization_id, request_id)]
        except KeyError as exc:
            raise KeyError("Genesis request tidak ditemukan") from exc

    def add_review(
        self,
        request_id: UUID,
        organization_id: UUID,
        reviewer_user_id: UUID,
        command: GenesisReviewCreate,
    ) -> GenesisPipelineView:
        view = self.get(request_id, organization_id)
        if view.status != GenesisLifecycleStatus.AWAITING_HUMAN_REVIEW:
            raise ValueError("Genesis request tidak berada pada human review")
        if any(review.gate == command.gate for review in view.reviews):
            raise ValueError(f"Review gate {command.gate} sudah diisi")
        review = GenesisReviewView(
            review_id=uuid4(),
            gate=command.gate,
            decision=command.decision,
            reviewer_user_id=reviewer_user_id,
            notes=command.notes,
            reviewed_at=datetime.now(UTC),
        )
        reviews = (*view.reviews, review)
        if command.decision == "REJECTED":
            status = GenesisLifecycleStatus.REJECTED
        elif {item.gate for item in reviews} == {"BUSINESS", "TECHNICAL"}:
            status = GenesisLifecycleStatus.APPROVED
        else:
            status = view.status
        updated = view.model_copy(
            update={
                "reviews": reviews,
                "status": status,
                "next_allowed_action": _next_action(status),
                "updated_at": datetime.now(UTC),
            }
        )
        self._records[(organization_id, request_id)] = updated
        return updated

    def stage(
        self,
        request_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
        contract: AgentDefinition,
    ) -> GenesisPipelineView:
        view = self.get(request_id, organization_id)
        if view.status != GenesisLifecycleStatus.APPROVED:
            raise ValueError("Genesis request belum mendapat dua approval")
        now = datetime.now(UTC)
        release = GenesisReleaseView(
            release_id=uuid4(),
            status="STAGED",
            contract_digest=contract.contract_digest,
            staged_by_user_id=actor_user_id,
            released_by_user_id=None,
            staged_at=now,
            released_at=None,
        )
        updated = view.model_copy(
            update={
                "status": GenesisLifecycleStatus.STAGED,
                "release": release,
                "next_allowed_action": "RELEASE_PACKAGE",
                "updated_at": now,
            }
        )
        self._records[(organization_id, request_id)] = updated
        return updated

    def release(
        self,
        request_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> GenesisPipelineView:
        view = self.get(request_id, organization_id)
        if view.status != GenesisLifecycleStatus.STAGED or view.release is None:
            raise ValueError("Genesis request belum berada pada staging")
        now = datetime.now(UTC)
        release = view.release.model_copy(
            update={
                "status": "RELEASED",
                "released_by_user_id": actor_user_id,
                "released_at": now,
            }
        )
        updated = view.model_copy(
            update={
                "status": GenesisLifecycleStatus.RELEASED,
                "release": release,
                "next_allowed_action": "SEPARATE_DEPLOYMENT_APPROVAL",
                "updated_at": now,
            }
        )
        self._records[(organization_id, request_id)] = updated
        return updated


class PostgresGenesisStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, view: GenesisPipelineView) -> GenesisPipelineView:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO genesis.change_requests
                        (request_id, organization_id, strategy, requested_by_user_id,
                         justification, source_references, request_payload, proposal_payload,
                         test_payload, status, production_effect, created_at, updated_at)
                    VALUES
                        (:request_id, :organization_id, :strategy, :requested_by_user_id,
                         :justification, CAST(:source_references AS jsonb),
                         CAST(:request_payload AS jsonb), CAST(:proposal_payload AS jsonb),
                         CAST(:test_payload AS jsonb), :status, false, :created_at, :updated_at)
                    """
                ),
                {
                    "request_id": view.request_id,
                    "organization_id": view.organization_id,
                    "strategy": view.strategy.value,
                    "requested_by_user_id": view.requested_by_user_id,
                    "justification": view.justification,
                    "source_references": json.dumps(view.source_references),
                    "request_payload": json.dumps(
                        {
                            "strategy": view.strategy.value,
                            "justification": view.justification,
                            "source_references": view.source_references,
                        }
                    ),
                    "proposal_payload": view.proposal.model_dump_json(),
                    "test_payload": json.dumps(
                        [item.model_dump(mode="json") for item in view.tests]
                    ),
                    "status": view.status.value,
                    "created_at": view.created_at,
                    "updated_at": view.updated_at,
                },
            )
            validation_passed = all(item.passed for item in view.proposal.validations)
            tests_passed = all(item.passed for item in view.tests)
            stages = (
                ("SOURCE", True),
                ("ANALYZE", True),
                ("GENERATE", view.proposal.resolved_contract is not None),
                ("VALIDATE", validation_passed),
                ("TEST", tests_passed),
                ("DIFF", True),
            )
            for stage, passed in stages:
                self._append_stage(
                    connection,
                    view.request_id,
                    stage,
                    view.requested_by_user_id,
                    {"status": "COMPLETED" if passed else "FAILED"},
                    view.created_at,
                )
        return view

    def get(self, request_id: UUID, organization_id: UUID) -> GenesisPipelineView:
        with self._engine.connect() as connection:
            return self._read(connection, request_id, organization_id)

    def add_review(
        self,
        request_id: UUID,
        organization_id: UUID,
        reviewer_user_id: UUID,
        command: GenesisReviewCreate,
    ) -> GenesisPipelineView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = self._lock_request(connection, request_id, organization_id)
            if row["status"] != GenesisLifecycleStatus.AWAITING_HUMAN_REVIEW.value:
                raise ValueError("Genesis request tidak berada pada human review")
            connection.execute(
                text(
                    """
                    INSERT INTO genesis.reviews
                        (review_id, request_id, gate, decision, reviewer_user_id,
                         notes, reviewed_at)
                    VALUES
                        (:review_id, :request_id, :gate, :decision, :reviewer_user_id,
                         :notes, :reviewed_at)
                    """
                ),
                {
                    "review_id": uuid4(),
                    "request_id": request_id,
                    "gate": command.gate.value,
                    "decision": command.decision.value,
                    "reviewer_user_id": reviewer_user_id,
                    "notes": command.notes,
                    "reviewed_at": now,
                },
            )
            decisions = connection.execute(
                text("SELECT gate, decision FROM genesis.reviews WHERE request_id = :request_id"),
                {"request_id": request_id},
            ).mappings().all()
            if any(item["decision"] == "REJECTED" for item in decisions):
                status = GenesisLifecycleStatus.REJECTED
            elif {item["gate"] for item in decisions} == {"BUSINESS", "TECHNICAL"}:
                status = GenesisLifecycleStatus.APPROVED
            else:
                status = GenesisLifecycleStatus.AWAITING_HUMAN_REVIEW
            connection.execute(
                text(
                    """
                    UPDATE genesis.change_requests
                    SET status = :status, updated_at = :updated_at
                    WHERE request_id = :request_id
                    """
                ),
                {"status": status.value, "updated_at": now, "request_id": request_id},
            )
            self._append_stage(
                connection,
                request_id,
                "HUMAN_REVIEW",
                reviewer_user_id,
                {"gate": command.gate.value, "decision": command.decision.value},
                now,
            )
            return self._read(connection, request_id, organization_id)

    def stage(
        self,
        request_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
        contract: AgentDefinition,
    ) -> GenesisPipelineView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = self._lock_request(connection, request_id, organization_id)
            if row["status"] != GenesisLifecycleStatus.APPROVED.value:
                raise ValueError("Genesis request belum mendapat dua approval")
            release_id = uuid4()
            connection.execute(
                text(
                    """
                    INSERT INTO genesis.release_packages
                        (release_id, request_id, contract_snapshot, contract_digest, status,
                         staged_by_user_id, production_effect, staged_at)
                    VALUES
                        (:release_id, :request_id, CAST(:contract_snapshot AS jsonb),
                         :contract_digest, 'STAGED', :actor_user_id, false, :staged_at)
                    """
                ),
                {
                    "release_id": release_id,
                    "request_id": request_id,
                    "contract_snapshot": contract.model_dump_json(),
                    "contract_digest": contract.contract_digest,
                    "actor_user_id": actor_user_id,
                    "staged_at": now,
                },
            )
            self._update_status(connection, request_id, GenesisLifecycleStatus.STAGED, now)
            self._append_stage(
                connection,
                request_id,
                "STAGING",
                actor_user_id,
                {"release_id": str(release_id), "production_effect": False},
                now,
            )
            return self._read(connection, request_id, organization_id)

    def release(
        self,
        request_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> GenesisPipelineView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = self._lock_request(connection, request_id, organization_id)
            if row["status"] != GenesisLifecycleStatus.STAGED.value:
                raise ValueError("Genesis request belum berada pada staging")
            connection.execute(
                text(
                    """
                    UPDATE genesis.release_packages
                    SET status = 'RELEASED', released_by_user_id = :actor_user_id,
                        released_at = :released_at
                    WHERE request_id = :request_id AND status = 'STAGED'
                    """
                ),
                {
                    "actor_user_id": actor_user_id,
                    "released_at": now,
                    "request_id": request_id,
                },
            )
            self._update_status(connection, request_id, GenesisLifecycleStatus.RELEASED, now)
            self._append_stage(
                connection,
                request_id,
                "RELEASE",
                actor_user_id,
                {"production_effect": False, "next": "SEPARATE_DEPLOYMENT_APPROVAL"},
                now,
            )
            return self._read(connection, request_id, organization_id)

    @staticmethod
    def _lock_request(connection: Any, request_id: UUID, organization_id: UUID) -> Any:
        row = connection.execute(
            text(
                """
                SELECT * FROM genesis.change_requests
                WHERE request_id = :request_id AND organization_id = :organization_id
                FOR UPDATE
                """
            ),
            {"request_id": request_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise KeyError("Genesis request tidak ditemukan")
        return row

    @staticmethod
    def _update_status(
        connection: Any,
        request_id: UUID,
        status: GenesisLifecycleStatus,
        now: datetime,
    ) -> None:
        connection.execute(
            text(
                """
                UPDATE genesis.change_requests SET status = :status, updated_at = :updated_at
                WHERE request_id = :request_id
                """
            ),
            {"status": status.value, "updated_at": now, "request_id": request_id},
        )

    @staticmethod
    def _append_stage(
        connection: Any,
        request_id: UUID,
        stage: str,
        actor_user_id: UUID,
        result: dict[str, object],
        occurred_at: datetime,
    ) -> None:
        connection.execute(
            text(
                """
                INSERT INTO genesis.stage_events
                    (stage_event_id, request_id, stage, actor_user_id,
                     result_payload, occurred_at)
                VALUES
                    (:stage_event_id, :request_id, :stage, :actor_user_id,
                     CAST(:result_payload AS jsonb), :occurred_at)
                """
            ),
            {
                "stage_event_id": uuid4(),
                "request_id": request_id,
                "stage": stage,
                "actor_user_id": actor_user_id,
                "result_payload": json.dumps(result),
                "occurred_at": occurred_at,
            },
        )

    @staticmethod
    def _read(connection: Any, request_id: UUID, organization_id: UUID) -> GenesisPipelineView:
        row = connection.execute(
            text(
                """
                SELECT * FROM genesis.change_requests
                WHERE request_id = :request_id AND organization_id = :organization_id
                """
            ),
            {"request_id": request_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise KeyError("Genesis request tidak ditemukan")
        review_rows = connection.execute(
            text(
                """
                SELECT review_id, gate, decision, reviewer_user_id, notes, reviewed_at
                FROM genesis.reviews WHERE request_id = :request_id ORDER BY reviewed_at
                """
            ),
            {"request_id": request_id},
        ).mappings().all()
        release_row = connection.execute(
            text("SELECT * FROM genesis.release_packages WHERE request_id = :request_id"),
            {"request_id": request_id},
        ).mappings().one_or_none()
        status = GenesisLifecycleStatus(row["status"])
        return GenesisPipelineView(
            request_id=row["request_id"],
            organization_id=row["organization_id"],
            strategy=row["strategy"],
            requested_by_user_id=row["requested_by_user_id"],
            justification=row["justification"],
            source_references=tuple(row["source_references"]),
            status=status,
            proposal=row["proposal_payload"],
            tests=tuple(row["test_payload"]),
            reviews=tuple(review_rows),
            release=(GenesisReleaseView.model_validate(release_row) if release_row else None),
            next_allowed_action=_next_action(status),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _next_action(status: GenesisLifecycleStatus) -> str:
    return {
        GenesisLifecycleStatus.INVALID: "CORRECT_SPECIFICATION",
        GenesisLifecycleStatus.AWAITING_HUMAN_REVIEW: "HUMAN_REVIEW",
        GenesisLifecycleStatus.REJECTED: "CLOSED_OR_RESUBMIT",
        GenesisLifecycleStatus.APPROVED: "STAGE_PACKAGE",
        GenesisLifecycleStatus.STAGED: "RELEASE_PACKAGE",
        GenesisLifecycleStatus.RELEASED: "SEPARATE_DEPLOYMENT_APPROVAL",
    }[status]
