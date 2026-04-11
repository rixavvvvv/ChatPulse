from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import Template, TemplateStatus


async def create_template(
    session: AsyncSession,
    workspace_id: int,
    name: str,
    body: str,
    variables: list[str],
) -> Template:
    template = Template(
        workspace_id=workspace_id,
        name=name,
        body=body,
        variables=variables,
        status=TemplateStatus.pending,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


async def list_templates(
    session: AsyncSession,
    workspace_id: int,
) -> list[Template]:
    stmt = (
        select(Template)
        .where(Template.workspace_id == workspace_id)
        .order_by(Template.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_template_by_id(
    session: AsyncSession,
    workspace_id: int,
    template_id: int,
) -> Template | None:
    stmt = select(Template).where(
        Template.workspace_id == workspace_id,
        Template.id == template_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_template_status(
    session: AsyncSession,
    template: Template,
    status: TemplateStatus,
) -> Template:
    template.status = status
    await session.commit()
    await session.refresh(template)
    return template
