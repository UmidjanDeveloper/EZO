"""Offline operator-only owner role management; never a public escalation endpoint.

python -m ezo_api.owner_admin --owner-email OWNER --grant --ack-owner-role-change
Requires private DATABASE_URL access. Never creates a user or prints credentials.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from ezo_api.db.models import User
from ezo_api.db.session import Database
from ezo_api.settings import Settings


async def change_owner_role(db: Database, owner_email: str, *, grant: bool) -> None:
    async with db.sessionmaker() as session, session.begin():
        user = await session.scalar(
            select(User).where(User.email == owner_email.lower()).with_for_update()
        )
        if user is None:
            raise ValueError("Existing authenticated owner account is required.")
        user.role = "super_admin" if grant else "user"


async def run(args: argparse.Namespace) -> None:
    settings = Settings()
    if args.owner_email.lower() != settings.owner_email.lower():
        raise ValueError("Email must exactly match the configured installation owner.")
    db = Database(settings.database_url)
    try:
        await change_owner_role(db, settings.owner_email, grant=args.grant)
    finally:
        await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-email", required=True)
    choices = parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--grant", action="store_true")
    choices.add_argument("--revoke", action="store_true")
    parser.add_argument("--ack-owner-role-change", action="store_true", required=True)
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception as exc:
        raise SystemExit("Owner role change failed (" + type(exc).__name__ + ").") from None
    print("Owner role updated. Authentication and consent rules remain enforced.")


if __name__ == "__main__":
    main()
