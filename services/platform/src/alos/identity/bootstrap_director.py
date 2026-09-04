"""Interactive, VPS-only setup for the first ALOS staging director password."""

from __future__ import annotations

import argparse
import getpass

from alos.config import get_settings
from alos.identity.authentication import BootstrapError, IdentityAuthenticationRepository

DEFAULT_DIRECTOR_EMAIL = "andararejomakmur10@gmail.com"


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap the ALOS staging director account.")
    parser.add_argument("--email", default=DEFAULT_DIRECTOR_EMAIL)
    parser.add_argument("--display-name", default="ALOS Director")
    parser.add_argument("--workspace-key", default="ALOS_GOVERNANCE")
    parser.add_argument("--workspace-name", default="ALOS Governance")
    arguments = parser.parse_args()
    password = getpass.getpass("New director password (minimum 16 characters): ")
    confirmation = getpass.getpass("Confirm director password: ")
    if password != confirmation:
        parser.error("password confirmation does not match")
    settings = get_settings()
    try:
        result = IdentityAuthenticationRepository(settings.database_url).bootstrap_director(
            email=arguments.email,
            password=password,
            display_name=arguments.display_name,
            workspace_key=arguments.workspace_key,
            workspace_name=arguments.workspace_name,
            settings=settings,
        )
    except BootstrapError as error:
        parser.error(str(error))
    print(f"Director bootstrap completed for workspace {result.workspace_key}.")


if __name__ == "__main__":
    main()
