"""H4 governance: no agent becomes active without independently recorded evidence."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.identity import DivisionCode, HumanRole
from alos.persistence.database import psycopg_url
from alos.runtime.service import AgentRunRequest, AgentRunResult

TestCategory = Literal["POSITIVE", "NEGATIVE", "REGRESSION", "SECURITY", "RECOVERY"]
ReviewGate = Literal["BUSINESS", "TECHNICAL"]
ReviewDecision = Literal["APPROVED", "REJECTED", "RETURNED"]
ReleaseState = Literal[
    "DRAFT",
    "TESTED",
    "IN_REVIEW",
    "RETURNED",
    "REJECTED",
    "APPROVED",
    "RELEASED",
    "ACTIVE",
    "SUSPENDED",
    "ROLLED_BACK",
]


class ReleaseGovernanceError(RuntimeError):
    """A safe lifecycle policy failure."""


class SegregationOfDutiesError(ReleaseGovernanceError):
    """One person attempted incompatible lifecycle duties."""


class LifecycleConflictError(ReleaseGovernanceError):
    """A transition lacks required evidence or is out of sequence."""


class TestCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    category: TestCategory
    input_fixture: dict[str, Any]
    expected_assertions: dict[str, Any]


class ReleaseRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    requirement: str = Field(min_length=20, max_length=10_000)


class ReasonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=10_000)


class TestCaseRecord(TestCaseRequest):
    test_case_id: UUID
    agent_key: str
    agent_version_id: UUID


class ReleaseRequestRecord(BaseModel):
    change_request_id: UUID
    agent_key: str
    agent_version_id: UUID
    semantic_version: str
    state: ReleaseState
    maker_user_id: UUID
    checker_user_id: UUID | None
    approver_user_id: UUID | None


class TestExecutionResult(BaseModel):
    test_run_id: UUID
    test_key: str
    status: Literal["PASSED", "FAILED", "BLOCKED", "ERROR"]
    agent_run_id: UUID | None


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate: ReviewGate
    decision: ReviewDecision
    notes: str = Field(min_length=1, max_length=10_000)


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_semantic_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    reason: str = Field(min_length=1, max_length=10_000)


LocalReleaseDuty = Literal[
    "MAKER", "CHECKER", "BUSINESS_REVIEWER", "TECHNICAL_REVIEWER", "APPROVER"
]


class LocalReleaseParticipant(BaseModel):
    """A local-only identity used to exercise human separation of duties."""

    duty: LocalReleaseDuty
    user_id: UUID
    email: str
    role: HumanRole


class LocalReleaseTeam(BaseModel):
    organization_id: UUID
    workspace_id: UUID
    division_code: DivisionCode
    participants: list[LocalReleaseParticipant]


Executor = Callable[[str, AgentRunRequest], AgentRunResult]


class AgentTestRunner:
    """Execute registered fixtures and persist result evidence before review."""

    def __init__(self, repository: ReleaseGovernanceRepository, executor: Executor) -> None:
        self._repository = repository
        self._executor = executor

    def execute(
        self,
        change_request_id: UUID,
        test_key: str,
        *,
        checker_user_id: UUID,
        correlation_id: UUID | None = None,
    ) -> TestExecutionResult:
        correlation_id = correlation_id or uuid4()
        self._repository.require_workspace_actor(change_request_id, checker_user_id)
        case = self._repository.get_test_case(change_request_id, test_key)
        requested_tools = case.input_fixture.get("requested_tool_keys", [])
        if not isinstance(requested_tools, list) or not all(
            isinstance(tool_key, str) for tool_key in requested_tools
        ):
            raise ReleaseGovernanceError("test fixture requested_tool_keys must be a string list")
        input_data = case.input_fixture.get("input", case.input_fixture)
        if not isinstance(input_data, dict):
            raise ReleaseGovernanceError("test fixture input must be an object")
        result = self._executor(
            case.agent_key,
            AgentRunRequest(
                workspace_id=self._repository.workspace_for_change(change_request_id),
                input=input_data,
                requested_tool_keys=requested_tools,
            ),
        )
        expected_status = case.expected_assertions.get("status")
        if expected_status not in {"SUCCEEDED", "FAILED", "BLOCKED"}:
            raise ReleaseGovernanceError("test expected_assertions.status is required")
        passed = result.status == expected_status
        return self._repository.record_test_result(
            change_request_id,
            case,
            checker_user_id=checker_user_id,
            correlation_id=correlation_id,
            passed=passed,
            agent_run_id=result.agent_run_id,
            result={"expected_status": expected_status, "actual_status": result.status},
        )


class ReleaseGovernanceRepository:
    """Database-backed SoD and lifecycle state machine."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def bootstrap_local_release_team(
        self, workspace_id: UUID, correlation_id: UUID
    ) -> LocalReleaseTeam:
        """Create idempotent local test identities; unavailable outside the local API route."""
        duties: tuple[tuple[LocalReleaseDuty, str, HumanRole, str], ...] = (
            ("MAKER", "h4-maker@alos.local", HumanRole.DIVISION_OWNER, "ALOS H4 Maker"),
            ("CHECKER", "h4-checker@alos.local", HumanRole.QA_SECURITY, "ALOS H4 Checker"),
            (
                "BUSINESS_REVIEWER",
                "h4-business-reviewer@alos.local",
                HumanRole.BUSINESS_REVIEWER,
                "ALOS H4 Business Reviewer",
            ),
            (
                "TECHNICAL_REVIEWER",
                "h4-technical-reviewer@alos.local",
                HumanRole.TECHNICAL_REVIEWER,
                "ALOS H4 Technical Reviewer",
            ),
            ("APPROVER", "h4-approver@alos.local", HumanRole.DIRECTOR, "ALOS H4 Approver"),
        )
        with self._transaction() as connection:
            workspace = connection.execute(
                """
                SELECT workspace.organization_id, workspace.division_id,
                       division.code AS division_code
                FROM workspace.workspaces AS workspace
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = workspace.division_id
                WHERE workspace.workspace_id = %s AND workspace.status = 'ACTIVE'
                """,
                (workspace_id,),
            ).fetchone()
            if workspace is None:
                raise ReleaseGovernanceError(
                    "an active workspace is required for the local review team"
                )
            division_id = workspace["division_id"]
            division_code = workspace["division_code"]
            if division_id is None or division_code is None:
                fallback_division = connection.execute(
                    """
                    SELECT division_id, code FROM identity.divisions
                    WHERE organization_id = %s AND code = 'IT'
                    """,
                    (workspace["organization_id"],),
                ).fetchone()
                if fallback_division is None:
                    raise ReleaseGovernanceError("a local review division could not be found")
                division_id = fallback_division["division_id"]
                division_code = fallback_division["code"]
            participants: list[LocalReleaseParticipant] = []
            for duty, email, role, display_name in duties:
                user = connection.execute(
                    """
                    INSERT INTO identity.users (organization_id, email, display_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (organization_id, email)
                    DO UPDATE SET display_name = EXCLUDED.display_name
                    RETURNING user_id, email
                    """,
                    (workspace["organization_id"], email, display_name),
                ).fetchone()
                if user is None:
                    raise ReleaseGovernanceError("a local review identity could not be created")
                connection.execute(
                    """
                    INSERT INTO workspace.memberships (workspace_id, user_id, access_level)
                    VALUES (%s, %s, 'EDITOR')
                    ON CONFLICT (workspace_id, user_id) DO NOTHING
                    """,
                    (workspace_id, user["user_id"]),
                )
                connection.execute(
                    """
                    INSERT INTO identity.role_assignments (user_id, division_id, role_code)
                    SELECT %s, %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM identity.role_assignments
                        WHERE user_id = %s AND role_code = %s AND revoked_at IS NULL
                    )
                    """,
                    (user["user_id"], division_id, role.value, user["user_id"], role.value),
                )
                participants.append(
                    LocalReleaseParticipant(
                        duty=duty,
                        user_id=user["user_id"],
                        email=user["email"],
                        role=role,
                    )
                )
            approver = next(item for item in participants if item.duty == "APPROVER")
            self._audit(
                connection,
                workspace["organization_id"],
                approver.user_id,
                "LOCAL_RELEASE_TEAM_BOOTSTRAPPED",
                "WORKSPACE",
                workspace_id,
                correlation_id,
                "Local-only H4 maker/checker/reviewer/approver test identities were prepared",
                {"duties": [participant.duty for participant in participants]},
            )
            return LocalReleaseTeam(
                organization_id=workspace["organization_id"],
                workspace_id=workspace_id,
                division_code=DivisionCode(division_code),
                participants=participants,
            )

    def create_release_request(
        self,
        agent_key: str,
        workspace_id: UUID,
        requirement: str,
        *,
        organization_id: UUID,
        maker_user_id: UUID,
        correlation_id: UUID,
    ) -> ReleaseRequestRecord:
        with self._transaction() as connection:
            self._require_workspace_actor(connection, organization_id, maker_user_id, workspace_id)
            version = self._draft_version(connection, organization_id, workspace_id, agent_key)
            change = connection.execute(
                """
                INSERT INTO genesis.change_requests (
                    organization_id, workspace_id, requested_by_user_id, requirement
                ) VALUES (%s, %s, %s, %s)
                RETURNING change_request_id
                """,
                (organization_id, workspace_id, maker_user_id, requirement),
            ).fetchone()
            if change is None:
                raise ReleaseGovernanceError("release request could not be created")
            connection.execute(
                """
                INSERT INTO governance.agent_change_requests (
                    change_request_id, agent_contract_id, agent_version_id, maker_user_id
                ) VALUES (%s, %s, %s, %s)
                """,
                (
                    change["change_request_id"],
                    version["agent_contract_id"],
                    version["agent_version_id"],
                    maker_user_id,
                ),
            )
            self._lifecycle_event(
                connection,
                change["change_request_id"],
                version["agent_version_id"],
                None,
                "DRAFT",
                maker_user_id,
                "Maker opened a release request for an immutable draft version",
                correlation_id,
            )
            self._audit(
                connection,
                organization_id,
                maker_user_id,
                "RELEASE_REQUEST_CREATED",
                "CHANGE_REQUEST",
                change["change_request_id"],
                correlation_id,
                "Maker opened a governed agent release request",
                {"agent_key": agent_key, "semantic_version": version["semantic_version"]},
            )
            return ReleaseRequestRecord(
                change_request_id=change["change_request_id"],
                agent_key=agent_key,
                agent_version_id=version["agent_version_id"],
                semantic_version=version["semantic_version"],
                state="DRAFT",
                maker_user_id=maker_user_id,
                checker_user_id=None,
                approver_user_id=None,
            )

    def register_test_case(
        self,
        change_request_id: UUID,
        request: TestCaseRequest,
        *,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> TestCaseRecord:
        with self._transaction() as connection:
            context = self._context(connection, change_request_id)
            self._require_context_actor(connection, context, actor_user_id)
            self._require_maker(context, actor_user_id)
            if context["state"] not in {"DRAFT", "RETURNED"}:
                raise LifecycleConflictError(
                    "test cases can only be registered for a draft or returned request"
                )
            row = connection.execute(
                """
                INSERT INTO governance.test_cases (
                    organization_id, agent_version_id, test_key, category,
                    input_fixture, expected_assertions
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING test_case_id
                """,
                (
                    context["organization_id"],
                    context["agent_version_id"],
                    request.test_key,
                    request.category,
                    Jsonb(request.input_fixture),
                    Jsonb(request.expected_assertions),
                ),
            ).fetchone()
            if row is None:
                raise ReleaseGovernanceError("test case could not be created")
            self._audit(
                connection,
                context["organization_id"],
                actor_user_id,
                "TEST_CASE_REGISTERED",
                "TEST_CASE",
                row["test_case_id"],
                correlation_id,
                "Maker registered a deterministic release test",
                {"change_request_id": str(change_request_id), "category": request.category},
            )
            return TestCaseRecord(
                test_case_id=row["test_case_id"],
                agent_key=context["agent_key"],
                agent_version_id=context["agent_version_id"],
                **request.model_dump(),
            )

    def get_test_case(self, change_request_id: UUID, test_key: str) -> TestCaseRecord:
        with self._connection() as connection:
            context = self._context(connection, change_request_id)
            case = connection.execute(
                """
                SELECT test_case_id, test_key, category, input_fixture, expected_assertions
                FROM governance.test_cases
                WHERE agent_version_id = %s AND test_key = %s
                """,
                (context["agent_version_id"], test_key),
            ).fetchone()
            if case is None:
                raise ReleaseGovernanceError("test case was not found for release request")
            return TestCaseRecord(
                test_case_id=case["test_case_id"],
                agent_key=context["agent_key"],
                agent_version_id=context["agent_version_id"],
                test_key=case["test_key"],
                category=case["category"],
                input_fixture=case["input_fixture"],
                expected_assertions=case["expected_assertions"],
            )

    def workspace_for_change(self, change_request_id: UUID) -> UUID:
        with self._connection() as connection:
            context = self._context(connection, change_request_id)
            return cast(UUID, context["workspace_id"])

    def require_workspace_actor(self, change_request_id: UUID, actor_user_id: UUID) -> None:
        """Deny operations by users who are outside the release request workspace."""
        with self._connection() as connection:
            context = self._context(connection, change_request_id)
            self._require_context_actor(connection, context, actor_user_id)

    def record_test_result(
        self,
        change_request_id: UUID,
        case: TestCaseRecord,
        *,
        checker_user_id: UUID,
        correlation_id: UUID,
        passed: bool,
        agent_run_id: UUID | None,
        result: dict[str, Any],
    ) -> TestExecutionResult:
        with self._transaction() as connection:
            context = self._context(connection, change_request_id)
            self._require_context_actor(connection, context, checker_user_id)
            self._require_checker(context, checker_user_id)
            if context["state"] not in {"DRAFT", "RETURNED"}:
                raise LifecycleConflictError(
                    "test results can only be recorded for a draft or returned request"
                )
            if case.agent_version_id != context["agent_version_id"]:
                raise LifecycleConflictError("test case does not belong to this release request")
            run = connection.execute(
                """
                INSERT INTO governance.test_runs (
                    test_case_id, agent_version_id, correlation_id, status, result, completed_at
                ) VALUES (%s, %s, %s, %s, %s, now())
                RETURNING test_run_id
                """,
                (
                    case.test_case_id,
                    context["agent_version_id"],
                    correlation_id,
                    "PASSED" if passed else "FAILED",
                    Jsonb({**result, "agent_run_id": str(agent_run_id) if agent_run_id else None}),
                ),
            ).fetchone()
            if run is None:
                raise ReleaseGovernanceError("test result could not be recorded")
            connection.execute(
                """
                UPDATE governance.agent_change_requests
                SET checker_user_id = coalesce(checker_user_id, %s)
                WHERE change_request_id = %s
                """,
                (checker_user_id, change_request_id),
            )
            self._audit(
                connection,
                context["organization_id"],
                checker_user_id,
                "TEST_EXECUTED",
                "TEST_RUN",
                run["test_run_id"],
                correlation_id,
                "Independent checker recorded a test result",
                {
                    "change_request_id": str(change_request_id),
                    "status": "PASSED" if passed else "FAILED",
                },
            )
            return TestExecutionResult(
                test_run_id=run["test_run_id"],
                test_key=case.test_key,
                status="PASSED" if passed else "FAILED",
                agent_run_id=agent_run_id,
            )

    def submit_for_review(
        self, change_request_id: UUID, *, checker_user_id: UUID, correlation_id: UUID
    ) -> ReleaseRequestRecord:
        with self._transaction() as connection:
            context = self._context(connection, change_request_id)
            self._require_context_actor(connection, context, checker_user_id)
            self._require_checker(context, checker_user_id)
            if context["state"] not in {"DRAFT", "RETURNED"}:
                raise LifecycleConflictError("only a draft or returned request can enter review")
            categories = connection.execute(
                """
                SELECT category, bool_and(latest.status = 'PASSED') AS passed
                FROM governance.test_cases AS test_case
                JOIN LATERAL (
                    SELECT status FROM governance.test_runs
                    WHERE test_case_id = test_case.test_case_id
                    ORDER BY completed_at DESC, test_run_id DESC LIMIT 1
                ) AS latest ON true
                WHERE test_case.agent_version_id = %s
                GROUP BY category
                """,
                (context["agent_version_id"],),
            ).fetchall()
            passed_categories = {row["category"] for row in categories if row["passed"]}
            required_categories = {"POSITIVE", "NEGATIVE", "REGRESSION", "SECURITY", "RECOVERY"}
            if not required_categories.issubset(passed_categories):
                raise LifecycleConflictError(
                    "positive, negative, regression, security, and recovery tests must pass"
                )
            successful_run = connection.execute(
                """
                SELECT 1 FROM runtime.agent_runs
                WHERE agent_version_id = %s AND status = 'SUCCEEDED'
                """,
                (context["agent_version_id"],),
            ).fetchone()
            if successful_run is None:
                raise LifecycleConflictError("a successful Agent Run is required before review")
            self._transition(
                connection,
                context,
                "TESTED",
                checker_user_id,
                "Independent checker confirmed all required tests passed",
                correlation_id,
            )
            self._transition(
                connection,
                context,
                "IN_REVIEW",
                checker_user_id,
                "Independent checker submitted immutable evidence for review",
                correlation_id,
            )
            return self._record_from_context(connection, change_request_id)

    def review(
        self,
        change_request_id: UUID,
        request: ReviewRequest,
        *,
        reviewer_user_id: UUID,
        correlation_id: UUID,
    ) -> ReleaseRequestRecord:
        with self._transaction() as connection:
            context = self._context(connection, change_request_id)
            self._require_context_actor(connection, context, reviewer_user_id)
            if context["state"] != "IN_REVIEW":
                raise LifecycleConflictError("request is not ready for review")
            self._require_reviewer(connection, context, reviewer_user_id)
            connection.execute(
                """
                INSERT INTO governance.reviews (
                    change_request_id, reviewer_user_id, review_gate, decision, notes
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    change_request_id,
                    reviewer_user_id,
                    request.gate,
                    request.decision,
                    request.notes,
                ),
            )
            if request.decision == "RETURNED":
                self._transition(
                    connection, context, "RETURNED", reviewer_user_id, request.notes, correlation_id
                )
            elif request.decision == "REJECTED":
                self._transition(
                    connection, context, "REJECTED", reviewer_user_id, request.notes, correlation_id
                )
            self._audit(
                connection,
                context["organization_id"],
                reviewer_user_id,
                "REVIEW_RECORDED",
                "CHANGE_REQUEST",
                change_request_id,
                correlation_id,
                request.notes,
                {"gate": request.gate, "decision": request.decision},
            )
            return self._record_from_context(connection, change_request_id)

    def approve(
        self, change_request_id: UUID, *, approver_user_id: UUID, correlation_id: UUID
    ) -> ReleaseRequestRecord:
        with self._transaction() as connection:
            context = self._context(connection, change_request_id)
            self._require_context_actor(connection, context, approver_user_id)
            if context["state"] != "IN_REVIEW":
                raise LifecycleConflictError("only an in-review request can be approved")
            self._require_approver(connection, context, approver_user_id)
            approvals = connection.execute(
                """
                SELECT review_gate FROM governance.reviews
                WHERE change_request_id = %s AND decision = 'APPROVED'
                """,
                (change_request_id,),
            ).fetchall()
            if {row["review_gate"] for row in approvals} != {"BUSINESS", "TECHNICAL"}:
                raise LifecycleConflictError("business and technical review approvals are required")
            connection.execute(
                """
                UPDATE governance.agent_change_requests SET approver_user_id = %s
                WHERE change_request_id = %s
                """,
                (approver_user_id, change_request_id),
            )
            self._transition(
                connection,
                context,
                "APPROVED",
                approver_user_id,
                "Independent approver accepted both review gates",
                correlation_id,
            )
            return self._record_from_context(connection, change_request_id)

    def release(
        self, change_request_id: UUID, *, approver_user_id: UUID, correlation_id: UUID
    ) -> ReleaseRequestRecord:
        with self._transaction() as connection:
            context = self._context(connection, change_request_id)
            self._require_context_actor(connection, context, approver_user_id)
            if context["state"] != "APPROVED" or context["approver_user_id"] != approver_user_id:
                raise LifecycleConflictError(
                    "only the recorded approver can release an approved request"
                )
            connection.execute(
                """
                INSERT INTO governance.release_proposals (
                    change_request_id, agent_version_id, target_environment, status
                )
                VALUES (%s, %s, 'STAGING', 'RELEASED')
                """,
                (change_request_id, context["agent_version_id"]),
            )
            self._transition(
                connection,
                context,
                "RELEASED",
                approver_user_id,
                "Approved version released to the internal staging lane",
                correlation_id,
            )
            return self._record_from_context(connection, change_request_id)

    def activate(
        self, change_request_id: UUID, *, approver_user_id: UUID, correlation_id: UUID
    ) -> ReleaseRequestRecord:
        with self._transaction() as connection:
            context = self._context(connection, change_request_id)
            self._require_context_actor(connection, context, approver_user_id)
            if context["state"] != "RELEASED" or context["approver_user_id"] != approver_user_id:
                raise LifecycleConflictError(
                    "only the recorded approver can activate a released request"
                )
            killed = connection.execute(
                """
                SELECT 1 FROM governance.kill_switches
                WHERE organization_id = %s AND agent_contract_id = %s AND active
                """,
                (context["organization_id"], context["agent_contract_id"]),
            ).fetchone()
            if killed is not None:
                raise LifecycleConflictError("kill switch is active")
            connection.execute(
                """
                UPDATE agents.registry
                SET released_version_id = %s, active_version_id = %s, updated_at = now()
                WHERE agent_contract_id = %s
                """,
                (
                    context["agent_version_id"],
                    context["agent_version_id"],
                    context["agent_contract_id"],
                ),
            )
            self._transition(
                connection,
                context,
                "ACTIVE",
                approver_user_id,
                "Released version became active after human approval",
                correlation_id,
            )
            return self._record_from_context(connection, change_request_id)

    def suspend(
        self, change_request_id: UUID, *, actor_user_id: UUID, reason: str, correlation_id: UUID
    ) -> ReleaseRequestRecord:
        with self._transaction() as connection:
            context = self._context(connection, change_request_id)
            self._require_context_actor(connection, context, actor_user_id)
            if context["state"] not in {"ACTIVE", "RELEASED"}:
                raise LifecycleConflictError("only released or active versions can be suspended")
            connection.execute(
                """
                UPDATE agents.registry SET active_version_id = NULL, updated_at = now()
                WHERE agent_contract_id = %s
                """,
                (context["agent_contract_id"],),
            )
            self._transition(
                connection, context, "SUSPENDED", actor_user_id, reason, correlation_id
            )
            return self._record_from_context(connection, change_request_id)

    def kill_switch(
        self, change_request_id: UUID, *, actor_user_id: UUID, reason: str, correlation_id: UUID
    ) -> ReleaseRequestRecord:
        with self._transaction() as connection:
            context = self._context(connection, change_request_id)
            self._require_context_actor(connection, context, actor_user_id)
            existing = connection.execute(
                """
                SELECT kill_switch_id FROM governance.kill_switches
                WHERE organization_id = %s AND agent_contract_id = %s AND active
                """,
                (context["organization_id"], context["agent_contract_id"]),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO governance.kill_switches (
                        organization_id, agent_contract_id, active, reason,
                        activated_by_user_id, activated_at
                    ) VALUES (%s, %s, true, %s, %s, now())
                    """,
                    (
                        context["organization_id"],
                        context["agent_contract_id"],
                        reason,
                        actor_user_id,
                    ),
                )
            connection.execute(
                """
                UPDATE agents.registry SET active_version_id = NULL, updated_at = now()
                WHERE agent_contract_id = %s
                """,
                (context["agent_contract_id"],),
            )
            self._transition(
                connection, context, "SUSPENDED", actor_user_id, reason, correlation_id
            )
            self._audit(
                connection,
                context["organization_id"],
                actor_user_id,
                "KILL_SWITCH_ACTIVATED",
                "AGENT_CONTRACT",
                context["agent_contract_id"],
                correlation_id,
                reason,
                {},
            )
            return self._record_from_context(connection, change_request_id)

    def rollback(
        self,
        change_request_id: UUID,
        request: RollbackRequest,
        *,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> ReleaseRequestRecord:
        with self._transaction() as connection:
            context = self._context(connection, change_request_id)
            self._require_context_actor(connection, context, actor_user_id)
            if context["state"] not in {"ACTIVE", "SUSPENDED"}:
                raise LifecycleConflictError(
                    "only an active or suspended version can be rolled back"
                )
            target = connection.execute(
                """
                SELECT agent_version_id, lifecycle_status FROM agents.versions
                WHERE agent_contract_id = %s AND semantic_version = %s
                """,
                (context["agent_contract_id"], request.target_semantic_version),
            ).fetchone()
            if target is None or target["agent_version_id"] == context["agent_version_id"]:
                raise LifecycleConflictError(
                    "rollback target must be a different version of the same agent"
                )
            if target["lifecycle_status"] not in {"ACTIVE", "SUSPENDED", "RELEASED"}:
                raise LifecycleConflictError("rollback target must have been released previously")
            active_kill_switch = connection.execute(
                """
                SELECT 1 FROM governance.kill_switches
                WHERE organization_id = %s AND agent_contract_id = %s AND active
                """,
                (context["organization_id"], context["agent_contract_id"]),
            ).fetchone()
            if active_kill_switch is not None:
                raise LifecycleConflictError("clear the active kill switch before rollback")
            connection.execute(
                """
                INSERT INTO governance.rollback_records (
                    agent_contract_id, from_version_id, to_version_id, reason, performed_by_user_id
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    context["agent_contract_id"],
                    context["agent_version_id"],
                    target["agent_version_id"],
                    request.reason,
                    actor_user_id,
                ),
            )
            connection.execute(
                """
                UPDATE agents.registry
                SET active_version_id = %s, released_version_id = %s, updated_at = now()
                WHERE agent_contract_id = %s
                """,
                (
                    target["agent_version_id"],
                    target["agent_version_id"],
                    context["agent_contract_id"],
                ),
            )
            self._transition(
                connection, context, "ROLLED_BACK", actor_user_id, request.reason, correlation_id
            )
            connection.execute(
                """
                UPDATE agents.versions SET lifecycle_status = 'ACTIVE'
                WHERE agent_version_id = %s
                """,
                (target["agent_version_id"],),
            )
            self._audit(
                connection,
                context["organization_id"],
                actor_user_id,
                "AGENT_ROLLED_BACK",
                "AGENT_CONTRACT",
                context["agent_contract_id"],
                correlation_id,
                request.reason,
                {"target_semantic_version": request.target_semantic_version},
            )
            return self._record_from_context(connection, change_request_id)

    def clear_kill_switch(
        self,
        change_request_id: UUID,
        *,
        actor_user_id: UUID,
        reason: str,
        correlation_id: UUID,
    ) -> ReleaseRequestRecord:
        """Require an explicit human action before a suspended agent can recover."""
        with self._transaction() as connection:
            context = self._context(connection, change_request_id)
            self._require_context_actor(connection, context, actor_user_id)
            cleared = connection.execute(
                """
                UPDATE governance.kill_switches
                SET active = false
                WHERE organization_id = %s AND agent_contract_id = %s AND active
                RETURNING kill_switch_id
                """,
                (context["organization_id"], context["agent_contract_id"]),
            ).fetchone()
            if cleared is None:
                raise LifecycleConflictError("there is no active kill switch to clear")
            self._audit(
                connection,
                context["organization_id"],
                actor_user_id,
                "KILL_SWITCH_CLEARED",
                "AGENT_CONTRACT",
                context["agent_contract_id"],
                correlation_id,
                reason,
                {},
            )
            return self._record_from_context(connection, change_request_id)

    def _transition(
        self,
        connection: psycopg.Connection[Any],
        context: dict[str, Any],
        state: ReleaseState,
        actor_user_id: UUID,
        reason: str,
        correlation_id: UUID,
    ) -> None:
        previous = context["state"]
        connection.execute(
            "UPDATE governance.agent_change_requests SET state = %s WHERE change_request_id = %s",
            (state, context["change_request_id"]),
        )
        change_status = "DRAFT" if state == "RETURNED" else state
        if change_status in {"ACTIVE", "SUSPENDED", "ROLLED_BACK"}:
            change_status = "RELEASED"
        connection.execute(
            "UPDATE genesis.change_requests SET status = %s WHERE change_request_id = %s",
            (change_status, context["change_request_id"]),
        )
        lifecycle_status = (
            state
            if state
            in {
                "DRAFT",
                "TESTED",
                "IN_REVIEW",
                "APPROVED",
                "RELEASED",
                "ACTIVE",
                "SUSPENDED",
                "ROLLED_BACK",
            }
            else "DRAFT"
        )
        connection.execute(
            "UPDATE agents.versions SET lifecycle_status = %s WHERE agent_version_id = %s",
            (lifecycle_status, context["agent_version_id"]),
        )
        self._lifecycle_event(
            connection,
            context["change_request_id"],
            context["agent_version_id"],
            previous,
            state,
            actor_user_id,
            reason,
            correlation_id,
        )
        self._audit(
            connection,
            context["organization_id"],
            actor_user_id,
            "AGENT_LIFECYCLE_TRANSITIONED",
            "AGENT_VERSION",
            context["agent_version_id"],
            correlation_id,
            reason,
            {"from": previous, "to": state},
        )

    def _record_from_context(
        self, connection: psycopg.Connection[Any], change_request_id: UUID
    ) -> ReleaseRequestRecord:
        context = self._context(connection, change_request_id)
        return ReleaseRequestRecord(**context)

    @staticmethod
    def _require_maker(context: dict[str, Any], actor_user_id: UUID) -> None:
        if context["maker_user_id"] != actor_user_id:
            raise SegregationOfDutiesError("only the maker may register release test cases")

    @staticmethod
    def _require_checker(context: dict[str, Any], checker_user_id: UUID) -> None:
        if checker_user_id == context["maker_user_id"]:
            raise SegregationOfDutiesError("maker cannot act as checker")
        recorded = context["checker_user_id"]
        if recorded is not None and recorded != checker_user_id:
            raise SegregationOfDutiesError("a release request has one independent checker")

    @staticmethod
    def _require_reviewer(
        connection: psycopg.Connection[Any], context: dict[str, Any], reviewer_user_id: UUID
    ) -> None:
        if reviewer_user_id in {context["maker_user_id"], context["checker_user_id"]}:
            raise SegregationOfDutiesError("maker or checker cannot act as reviewer")
        other_reviewers = connection.execute(
            "SELECT reviewer_user_id FROM governance.reviews WHERE change_request_id = %s",
            (context["change_request_id"],),
        ).fetchall()
        if reviewer_user_id in {row["reviewer_user_id"] for row in other_reviewers}:
            raise SegregationOfDutiesError("one reviewer may not satisfy multiple review gates")

    @staticmethod
    def _require_approver(
        connection: psycopg.Connection[Any], context: dict[str, Any], approver_user_id: UUID
    ) -> None:
        if approver_user_id in {context["maker_user_id"], context["checker_user_id"]}:
            raise SegregationOfDutiesError("maker or checker cannot act as approver")
        reviewers = connection.execute(
            "SELECT reviewer_user_id FROM governance.reviews WHERE change_request_id = %s",
            (context["change_request_id"],),
        ).fetchall()
        if approver_user_id in {row["reviewer_user_id"] for row in reviewers}:
            raise SegregationOfDutiesError("reviewer cannot act as approver")

    @staticmethod
    def _require_workspace_actor(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        user_id: UUID,
        workspace_id: UUID,
    ) -> None:
        actor = connection.execute(
            """
            SELECT 1 FROM identity.users AS user_account
            JOIN workspace.memberships AS membership ON membership.user_id = user_account.user_id
            WHERE user_account.organization_id = %s AND user_account.user_id = %s
              AND membership.workspace_id = %s
            """,
            (organization_id, user_id, workspace_id),
        ).fetchone()
        if actor is None:
            raise ReleaseGovernanceError("active workspace membership is required")

    @staticmethod
    def _require_context_actor(
        connection: psycopg.Connection[Any], context: dict[str, Any], actor_user_id: UUID
    ) -> None:
        ReleaseGovernanceRepository._require_workspace_actor(
            connection,
            context["organization_id"],
            actor_user_id,
            context["workspace_id"],
        )

    @staticmethod
    def _draft_version(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        workspace_id: UUID,
        agent_key: str,
    ) -> dict[str, Any]:
        version = connection.execute(
            """
            SELECT contract.agent_contract_id, version.agent_version_id, version.semantic_version
            FROM agents.contracts AS contract
            JOIN agents.versions AS version
              ON version.agent_contract_id = contract.agent_contract_id
            WHERE contract.organization_id = %s AND contract.workspace_id = %s
              AND contract.agent_key = %s AND version.lifecycle_status = 'DRAFT'
            ORDER BY version.created_at DESC, version.agent_version_id DESC LIMIT 1
            """,
            (organization_id, workspace_id, agent_key),
        ).fetchone()
        if version is None:
            raise LifecycleConflictError("a DRAFT Agent Contract version is required")
        return dict(version)

    @staticmethod
    def _context(connection: psycopg.Connection[Any], change_request_id: UUID) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT request.change_request_id, request.organization_id, request.workspace_id,
                   governance.agent_contract_id, governance.agent_version_id,
                   governance.maker_user_id,
                   governance.checker_user_id, governance.approver_user_id, governance.state,
                   contract.agent_key, version.semantic_version
            FROM genesis.change_requests AS request
            JOIN governance.agent_change_requests AS governance
              ON governance.change_request_id = request.change_request_id
            JOIN agents.contracts AS contract
              ON contract.agent_contract_id = governance.agent_contract_id
            JOIN agents.versions AS version
              ON version.agent_version_id = governance.agent_version_id
            WHERE request.change_request_id = %s
            """,
            (change_request_id,),
        ).fetchone()
        if row is None:
            raise ReleaseGovernanceError("release request was not found")
        return dict(row)

    @staticmethod
    def _lifecycle_event(
        connection: psycopg.Connection[Any],
        change_request_id: UUID,
        agent_version_id: UUID,
        from_state: str | None,
        to_state: str,
        actor_user_id: UUID,
        reason: str,
        correlation_id: UUID,
    ) -> None:
        connection.execute(
            """
            INSERT INTO governance.agent_lifecycle_events (
                change_request_id, agent_version_id, from_state, to_state,
                actor_user_id, reason, correlation_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                change_request_id,
                agent_version_id,
                from_state,
                to_state,
                actor_user_id,
                reason,
                correlation_id,
            ),
        )

    @staticmethod
    def _audit(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        actor_user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        correlation_id: UUID,
        reason: str,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'HUMAN', %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                organization_id,
                actor_user_id,
                action,
                entity_type,
                entity_id,
                correlation_id,
                reason,
                Jsonb(metadata),
            ),
        )

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection

    @contextmanager
    def _transaction(self) -> Iterator[psycopg.Connection[Any]]:
        with self._connection() as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
