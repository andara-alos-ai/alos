import os
from uuid import uuid4

import psycopg
import pytest

from alos.config import get_settings
from alos.entrypoints.api import database_for_url
from alos.persistence.migrations import psycopg_url
from alos.platform.identity import PilotProfileStore
from alos.security import Role

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]


def test_pilot_profile_store_derives_only_active_synthetic_assignments() -> None:
    suffix = uuid4().hex[:10]
    organization_id = uuid4()
    division_id = uuid4()
    project_id = uuid4()
    user_id = uuid4()
    organization_code = f"PT{suffix.upper()}"
    project_code = f"PILOT-{suffix.upper()}"
    email_domain = f"{suffix}.example.test"
    email = f"finance.pilot@{email_domain}"
    database_url = psycopg_url(get_settings().database_url)

    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO identity.organizations (organization_id, code, name) VALUES (%s, %s, %s)",
            (organization_id, organization_code, "Organisasi Pilot Test"),
        )
        connection.execute(
            """
            INSERT INTO identity.divisions (division_id, organization_id, code, name)
            VALUES (%s, %s, 'FINANCE', 'Keuangan')
            """,
            (division_id, organization_id),
        )
        connection.execute(
            """
            INSERT INTO identity.users
                (user_id, organization_id, email, display_name, status)
            VALUES (%s, %s, %s, 'Keuangan Pilot Test', 'ACTIVE')
            """,
            (user_id, organization_id, email),
        )
        connection.execute(
            """
            INSERT INTO identity.role_assignments
                (user_id, division_id, role_code, reason, created_by)
            VALUES (%s, %s, 'FINANCE', 'Controlled pilot identity test.', %s)
            """,
            (user_id, division_id, user_id),
        )
        connection.execute(
            """
            INSERT INTO platform.projects
                (project_id, organization_id, code, name, status, created_by)
            VALUES (%s, %s, %s, 'Proyek Pilot Test', 'ACTIVE', %s)
            """,
            (project_id, organization_id, project_code, user_id),
        )
        connection.execute(
            """
            INSERT INTO identity.project_assignments
                (user_id, project_id, reason, created_by)
            VALUES (%s, %s, 'Controlled pilot project test.', %s)
            """,
            (user_id, project_id, user_id),
        )

    try:
        engine = database_for_url(get_settings().database_url).engine
        store = PilotProfileStore(engine, project_code, email_domain)

        profile = store.get_profile(user_id)

        assert profile.email == email
        assert profile.roles == {Role.FINANCE}
        assert profile.division_codes == {"FINANCE"}
        assert profile.project_ids == {project_id}
        assert profile.to_principal().can_access_project(project_id)

        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE identity.users SET status = 'SUSPENDED' WHERE user_id = %s",
                (user_id,),
            )
        assert store.list_profiles() == ()
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM identity.project_assignments WHERE user_id = %s", (user_id,)
            )
            connection.execute(
                "DELETE FROM identity.role_assignments WHERE user_id = %s", (user_id,)
            )
            connection.execute("DELETE FROM platform.projects WHERE project_id = %s", (project_id,))
            connection.execute("DELETE FROM identity.users WHERE user_id = %s", (user_id,))
            connection.execute(
                "DELETE FROM identity.divisions WHERE division_id = %s", (division_id,)
            )
            connection.execute(
                "DELETE FROM identity.organizations WHERE organization_id = %s",
                (organization_id,),
            )
