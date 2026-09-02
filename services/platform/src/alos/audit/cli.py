from alos.audit.integrity import verify_audit_chains
from alos.config import get_settings


def main() -> None:
    report = verify_audit_chains(get_settings().database_url)
    if not report.valid:
        details = ", ".join(
            f"{issue.audit_entry_id}: {issue.reason}" for issue in report.issues[:10]
        )
        raise SystemExit(f"Audit chain TIDAK VALID ({len(report.issues)} temuan): {details}")
    print(
        "Audit chain valid: "
        f"{report.checked_entries} entri, {report.checked_organizations} organisasi"
    )


if __name__ == "__main__":
    main()
