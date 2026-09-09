"""Interactive, VPS-only setup for an ALOS staging IT Lead password."""

from __future__ import annotations

import argparse
import getpass

from alos.config import get_settings
from alos.identity.authentication import BootstrapError, IdentityAuthenticationRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap an ALOS staging IT Lead account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", default="ALOS IT Lead")
    parser.add_argument("--workspace-key", default="ALOS_GOVERNANCE")
    parser.add_argument(
        "--replace-director-role",
        action="store_true",
        help="convert an existing account with only the DIRECTOR role into IT_LEAD",
    )
    arguments = parser.parse_args()
    password = getpass.getpass("IT Lead password (minimum 16 characters): ")
    confirmation = getpass.getpass("Confirm IT Lead password: ")
    if password != confirmation:
        parser.error("password confirmation does not match")
    settings = get_settings()
    try:
        result = IdentityAuthenticationRepository(settings.database_url).bootstrap_it_lead(
            email=arguments.email,
            password=password,
            display_name=arguments.display_name,
            workspace_key=arguments.workspace_key,
            replace_director_role=arguments.replace_director_role,
            settings=settings,
        )
    except BootstrapError as error:
        parser.error(str(error))
    print(f"IT Lead bootstrap completed for workspace {result.workspace_key}.")


if __name__ == "__main__":
    main()
