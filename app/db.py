from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.base import Base

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    # Ensure model metadata is loaded before create_all executes.
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'user'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS subscription_plan VARCHAR(32) NOT NULL DEFAULT 'free'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO plans (name, message_limit, price) "
                "VALUES ('free', 1000, 0.00) "
                "ON CONFLICT (name) DO NOTHING"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO plans (name, message_limit, price) "
                "VALUES ('pro', 10000, 29.00) "
                "ON CONFLICT (name) DO NOTHING"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO plans (name, message_limit, price) "
                "VALUES ('business', 50000, 99.00) "
                "ON CONFLICT (name) DO NOTHING"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO plans (name, message_limit, price) "
                "VALUES ('enterprise', 200000, 299.00) "
                "ON CONFLICT (name) DO NOTHING"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO user_subscriptions (user_id, plan_id, status) "
                "SELECT u.id, COALESCE(p.id, free_plan.id), 'active' "
                "FROM users u "
                "JOIN plans free_plan ON free_plan.name = 'free' "
                "LEFT JOIN plans p ON p.name = u.subscription_plan "
                "LEFT JOIN user_subscriptions us ON us.user_id = u.id "
                "WHERE us.user_id IS NULL"
            )
        )
