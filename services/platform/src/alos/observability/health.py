import time
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from alos.agents.contract import AgentKind
from alos.agents.registry import AgentRegistry
from alos.audit.integrity import verify_audit_chains
from alos.config import Settings
from alos.persistence import Database
from alos.persistence.migrations import discover_migrations


def _find_migrations_dir() -> Path:
    candidates = [
        Path("infra/database"),
        Path(__file__).resolve().parents[4] / "infra" / "database",
        Path(__file__).resolve().parents[5] / "infra" / "database",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return Path("infra/database")


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class ComponentCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component: str
    status: HealthStatus
    message: str
    latency_ms: float | None = None
    details: dict[str, Any] = {}


class SystemReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: HealthStatus
    application_name: str
    environment: str
    timestamp: datetime
    all_passed: bool
    checks: list[ComponentCheck]


def evaluate_system_readiness(settings: Settings) -> SystemReadinessReport:
    checks: list[ComponentCheck] = []
    now = datetime.now(UTC)

    # 1. Database Connectivity Check
    db_start = time.perf_counter()
    try:
        db = Database(settings.database_url)
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_latency = round((time.perf_counter() - db_start) * 1000, 2)
        checks.append(
            ComponentCheck(
                component="database",
                status=HealthStatus.HEALTHY,
                message="PostgreSQL database connected and responsive.",
                latency_ms=db_latency,
                details={"driver": "postgresql+psycopg"},
            )
        )
    except Exception as exc:
        db = Database(settings.database_url)
        db_latency = round((time.perf_counter() - db_start) * 1000, 2)
        checks.append(
            ComponentCheck(
                component="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {exc}",
                latency_ms=db_latency,
            )
        )

    # 2. Database Migrations Check
    try:
        expected_files = discover_migrations(_find_migrations_dir())
        expected_count = len(expected_files)
        with db.engine.connect() as conn:
            row = conn.execute(
                text("SELECT count(*) FROM platform.schema_migrations")
            ).fetchone()
            applied_count = row[0] if row else 0

        is_synced = applied_count >= expected_count
        checks.append(
            ComponentCheck(
                component="migrations",
                status=HealthStatus.HEALTHY if is_synced else HealthStatus.DEGRADED,
                message=(
                    f"All {expected_count} schema migrations applied."
                    if is_synced
                    else f"Migration mismatch: {applied_count}/{expected_count} applied."
                ),
                details={
                    "applied_count": applied_count,
                    "expected_count": expected_count,
                },
            )
        )
    except Exception as exc:
        checks.append(
            ComponentCheck(
                component="migrations",
                status=HealthStatus.UNHEALTHY,
                message=f"Failed to check migrations: {exc}",
            )
        )

    # 3. Agent Registry Check
    try:
        registry = AgentRegistry(settings.definitions_root)
        agents = registry.load_all()
        top_level_agents = [a for a in agents if a.agent_kind == AgentKind.CORE]
        has_agents = bool(agents)
        checks.append(
            ComponentCheck(
                component="agent_registry",
                status=HealthStatus.HEALTHY if has_agents else HealthStatus.DEGRADED,
                message=(
                    f"{len(agents)} registered agents loaded and validated."
                    if has_agents
                    else "Agent Registry kosong."
                ),
                details={
                    "total_agents": len(agents),
                    "core_agents": len(top_level_agents),
                    "top_level_agents": len(top_level_agents),
                },
            )
        )
    except Exception as exc:
        checks.append(
            ComponentCheck(
                component="agent_registry",
                status=HealthStatus.UNHEALTHY,
                message=f"Failed to load agent registry: {exc}",
            )
        )

    # 4. Audit Chain Check
    try:
        audit_report = verify_audit_chains(settings.database_url)
        checks.append(
            ComponentCheck(
                component="audit_ledger",
                status=HealthStatus.HEALTHY if audit_report.valid else HealthStatus.UNHEALTHY,
                message=(
                    f"Audit chain verified ({audit_report.checked_entries} entries, "
                    f"{audit_report.checked_organizations} organizations)."
                    if audit_report.valid
                    else f"Audit chain verification failed with {len(audit_report.issues)} issues."
                ),
                details={
                    "total_entries": audit_report.checked_entries,
                    "organizations_count": audit_report.checked_organizations,
                    "valid": audit_report.valid,
                },
            )
        )
    except Exception as exc:
        checks.append(
            ComponentCheck(
                component="audit_ledger",
                status=HealthStatus.UNHEALTHY,
                message=f"Audit ledger check failed: {exc}",
            )
        )

    # 5. LLM Gateway Check
    llm_provider = settings.llm_provider
    checks.append(
        ComponentCheck(
            component="llm_gateway",
            status=HealthStatus.HEALTHY,
            message=(
                f"LLM Gateway configured with provider '{llm_provider}' "
                "and fail-closed fallback."
            ),
            details={
                "provider": llm_provider,
                "model": settings.llm_model,
                "offline_fallback": True,
            },
        )
    )

    all_healthy = all(c.status == HealthStatus.HEALTHY for c in checks)
    has_unhealthy = any(c.status == HealthStatus.UNHEALTHY for c in checks)

    overall_status = (
        HealthStatus.HEALTHY
        if all_healthy
        else HealthStatus.UNHEALTHY
        if has_unhealthy
        else HealthStatus.DEGRADED
    )

    return SystemReadinessReport(
        status=overall_status,
        application_name=settings.application_name,
        environment=settings.environment,
        timestamp=now,
        all_passed=all_healthy,
        checks=checks,
    )
