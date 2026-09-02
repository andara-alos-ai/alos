import sys

from alos.config import get_settings
from alos.observability.health import HealthStatus, evaluate_system_readiness


def main() -> None:
    settings = get_settings()
    report = evaluate_system_readiness(settings)

    print("=" * 70)
    print(f" ALOS SYSTEM READINESS CHECK — {report.application_name.upper()}")
    print(f" Environment : {report.environment.upper()}")
    print(f" Timestamp   : {report.timestamp.isoformat()}")
    print(f" Status      : {report.status.value}")
    print("=" * 70)

    for check in report.checks:
        icon = (
            "[PASS]"
            if check.status == HealthStatus.HEALTHY
            else "[WARN]"
            if check.status == HealthStatus.DEGRADED
            else "[FAIL]"
        )
        latency_str = (
            f" ({check.latency_ms} ms)" if check.latency_ms is not None else ""
        )
        print(f" {icon:<7} {check.component:<18} : {check.message}{latency_str}")

    print("=" * 70)

    if report.status == HealthStatus.UNHEALTHY:
        print(" [!] System is UNHEALTHY. Deployment readiness check FAILED.")
        sys.exit(1)
    elif report.status == HealthStatus.DEGRADED:
        print(" [!] System is DEGRADED. Review warnings before proceeding.")
        sys.exit(0)
    else:
        print(" [*] All platform components are READY for operational traffic.")
        sys.exit(0)


if __name__ == "__main__":
    main()
