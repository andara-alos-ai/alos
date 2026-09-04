"""Interactive, VPS-only setup for one independent H4 staging duty account."""

from __future__ import annotations

import argparse
import getpass

from alos.config import get_settings
from alos.identity.authentication import BootstrapError, IdentityAuthenticationRepository
from alos.identity.models import HumanRole


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap one ALOS H4 staging duty account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument(
        "--role",
        choices=[
            HumanRole.QA_SECURITY.value,
            HumanRole.BUSINESS_REVIEWER.value,
            HumanRole.TECHNICAL_REVIEWER.value,
            HumanRole.DIRECTOR.value,
        ],
        required=True,
    )
    parser.add_argument("--workspace-key", default="ALOS_GOVERNANCE")
    arguments = parser.parse_args()
    password = getpass.getpass("Password (minimum 16 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        parser.error("password confirmation does not match")
    try:
        repository = IdentityAuthenticationRepository(get_settings().database_url)
        result = repository.bootstrap_release_participant(
            email=arguments.email,
            password=password,
            display_name=arguments.display_name,
            role=HumanRole(arguments.role),
            workspace_key=arguments.workspace_key,
            settings=get_settings(),
        )
    except BootstrapError as error:
        parser.error(str(error))
    print(f"H4 {arguments.role} bootstrap completed for workspace {result.workspace_key}.")


if __name__ == "__main__":
    main()
