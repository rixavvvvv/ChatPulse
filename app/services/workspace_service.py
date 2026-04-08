from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import Membership, MembershipRole
from app.models.workspace import Workspace


async def create_workspace_with_owner_membership(
    session: AsyncSession,
    name: str,
    owner_id: int,
) -> Workspace:
    workspace = Workspace(name=name, owner_id=owner_id)
    session.add(workspace)
    await session.flush()

    membership = Membership(
        user_id=owner_id,
        workspace_id=workspace.id,
        role=MembershipRole.admin,
    )
    session.add(membership)

    await session.commit()
    await session.refresh(workspace)
    return workspace


async def get_user_membership(
    session: AsyncSession,
    user_id: int,
    workspace_id: int,
) -> Membership | None:
    stmt = select(Membership).where(
        Membership.user_id == user_id,
        Membership.workspace_id == workspace_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_user_workspaces(
    session: AsyncSession,
    user_id: int,
) -> list[tuple[Workspace, MembershipRole]]:
    stmt = (
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user_id)
        .order_by(Workspace.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.all())


async def get_default_workspace_id_for_user(
    session: AsyncSession,
    user_id: int,
) -> int | None:
    stmt = (
        select(Membership.workspace_id)
        .where(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def build_default_workspace_name(email: str) -> str:
    name_part = email.split("@", maxsplit=1)[0].strip()
    if not name_part:
        return "My Workspace"
    return f"{name_part.title()} Workspace"
