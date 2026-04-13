from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.base import Base

settings = get_settings()

engine_kwargs: dict = {
    "echo": settings.debug,
    "pool_pre_ping": True,
}

if settings.database_use_null_pool:
    engine_kwargs["poolclass"] = NullPool
else:
    engine_kwargs["pool_size"] = settings.database_pool_size
    engine_kwargs["max_overflow"] = settings.database_max_overflow
    engine_kwargs["pool_timeout"] = settings.database_pool_timeout_seconds
    engine_kwargs["pool_recycle"] = settings.database_pool_recycle_seconds

engine = create_async_engine(
    settings.database_url,
    **engine_kwargs,
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
                "DO $$ "
                "BEGIN "
                "  IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'template_status') THEN "
                "    ALTER TYPE template_status ADD VALUE IF NOT EXISTS 'draft'; "
                "  END IF; "
                "END $$;"
            )
        )
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS language VARCHAR(32) NOT NULL DEFAULT 'en_US'"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS category VARCHAR(32) NOT NULL DEFAULT 'MARKETING'"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS header_type VARCHAR(16) NOT NULL DEFAULT 'none'"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS header_content TEXT"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS body_text TEXT NOT NULL DEFAULT ''"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS body_examples JSONB NOT NULL DEFAULT '[]'::jsonb"))
        await conn.execute(text("UPDATE templates SET body_text = body WHERE body_text = '' AND body IS NOT NULL"))
        await conn.execute(text("UPDATE templates SET body = body_text WHERE body IS NULL AND body_text <> ''"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS footer_text TEXT"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS buttons JSONB NOT NULL DEFAULT '[]'::jsonb"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS meta_template_id VARCHAR(128)"))
        await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS rejection_reason TEXT"))
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
