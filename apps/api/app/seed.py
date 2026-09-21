"""Seed the super_admin user on first run."""

import asyncio

from sqlalchemy import select

from app.config import settings
from app.db import async_session_factory
from app.auth.security import hash_password
from app.models.user import User, UserRole


async def seed_super_admin() -> None:
    """Create the super_admin user if it doesn't exist."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == settings.SUPER_ADMIN_EMAIL)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"[seed] Super admin already exists: {settings.SUPER_ADMIN_EMAIL}")
            return

        user = User(
            email=settings.SUPER_ADMIN_EMAIL,
            password_hash=hash_password(settings.SUPER_ADMIN_PASSWORD),
            name=settings.SUPER_ADMIN_NAME,
            role=UserRole.super_admin,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"[seed] Created super admin: {settings.SUPER_ADMIN_EMAIL}")


if __name__ == "__main__":
    asyncio.run(seed_super_admin())
