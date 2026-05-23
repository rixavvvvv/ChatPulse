"""Database bootstrap service for local development."""

from datetime import UTC, datetime, timedelta
import logging
import random

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User, UserRole
from app.models.workspace import Workspace
from app.models.contact import Contact
from app.models.contact_intelligence import (
    Segment,
    ContactAttributeValue,
    AttributeDefinition,
    ContactActivity,
    Tag,
)
from app.models.template import Template, TemplateStatus
from app.models.campaign import Campaign, CampaignStatus
from app.models.conversation import Conversation, ConversationMessage
from app.models.workflow import WorkflowDefinition

from app.bootstrap.seed_data import (
    DEMO_WORKSPACE,
    DEMO_USER,
    DEMO_CONTACTS,
    DEMO_TAGS,
    DEMO_ATTRIBUTE_DEFINITIONS,
    DEMO_SEGMENTS,
    DEMO_TEMPLATES,
    DEMO_CAMPAIGNS,
    DEMO_CONVERSATIONS,
    DEMO_WORKFLOWS,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class BootstrapService:
    """Service to bootstrap the database with demo data."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.workspace_id: int | None = None
        self.user_id: int | None = None
        self.attribute_definition_map: dict[str, int] = {}

    async def bootstrap(self, reset: bool = False) -> dict[str, int]:
        """Run the full bootstrap process."""
        logger.info("Starting database bootstrap...")

        if reset:
            await self.reset_data()
            logger.info("Existing data reset")

        # Create workspace
        workspace = await self._create_workspace()
        self.workspace_id = workspace.id
        logger.info(
            f"Created workspace: {workspace.name} (ID: {workspace.id})")

        # Create user
        user = await self._create_user(workspace.id)
        self.user_id = user.id
        logger.info(f"Created user: {user.email} (ID: {user.id})")

        # Create tags
        tags = await self._create_tags()
        logger.info(f"Created {len(tags)} tags")

        # Create attribute definitions
        attr_defs = await self._create_attribute_definitions()
        logger.info(f"Created {len(attr_defs)} attribute definitions")

        # Create contacts
        contacts = await self._create_contacts()
        logger.info(f"Created {len(contacts)} contacts")

        # Create segments
        segments = await self._create_segments()
        logger.info(f"Created {len(segments)} segments")

        # Create templates
        templates = await self._create_templates()
        logger.info(f"Created {len(templates)} templates")

        # Create campaigns
        campaigns = await self._create_campaigns(contacts)
        logger.info(f"Created {len(campaigns)} campaigns")

        # Create workflows
        workflows = await self._create_workflows()
        logger.info(f"Created {len(workflows)} workflows")

        # Create conversations and messages
        conv_count, msg_count = await self._create_conversations(contacts)
        logger.info(
            f"Created {conv_count} conversations with {msg_count} messages")

        # Create analytics
        # Create contact activities
        await self._create_activities(contacts)
        logger.info("Created contact activities")

        stats = {
            "workspaces": 1,
            "users": 1,
            "tags": len(tags),
            "attribute_definitions": len(attr_defs),
            "contacts": len(contacts),
            "segments": len(segments),
            "templates": len(templates),
            "campaigns": len(campaigns),
            "workflows": len(workflows),
            "conversations": conv_count,
            "messages": msg_count,
            "analytics_days": 0,
        }

        logger.info(f"Bootstrap complete: {stats}")
        return stats

    async def reset_data(self) -> None:
        """Reset all demo data (keep structure)."""
        await self.session.execute(delete(ConversationMessage))
        await self.session.execute(delete(Conversation))
        await self.session.execute(delete(WorkflowDefinition))
        await self.session.execute(delete(Campaign))
        await self.session.execute(delete(Template))
        await self.session.execute(delete(Segment))
        await self.session.execute(delete(ContactAttributeValue))
        await self.session.execute(delete(AttributeDefinition))
        await self.session.execute(delete(ContactActivity))
        await self.session.execute(delete(Contact))
        await self.session.execute(delete(Tag))
        await self.session.execute(delete(User))
        await self.session.execute(delete(Workspace))
        await self.session.commit()

    async def _create_workspace(self) -> Workspace:
        """Create the demo workspace."""
        workspace = Workspace(
            name=DEMO_WORKSPACE["name"],
            slug=DEMO_WORKSPACE["slug"],
            description=DEMO_WORKSPACE["description"],
            created_at=datetime.now(UTC),
        )
        self.session.add(workspace)
        await self.session.flush()
        return workspace

    async def _create_user(self, workspace_id: int) -> User:
        """Create the demo user."""
        from app.models.membership import Membership, MembershipRole
        from app.services.auth_service import hash_password

        role = UserRole.user
        if DEMO_USER.get("role") == "admin":
            role = UserRole.super_admin

        user = User(
            email=DEMO_USER["email"],
            password_hash=hash_password(DEMO_USER["password"]),
            role=role.value,
            is_active=True,
            subscription_plan="free",
            created_at=datetime.now(UTC),
        )
        self.session.add(user)
        await self.session.flush()

        membership = Membership(
            user_id=user.id,
            workspace_id=workspace_id,
            role=MembershipRole.admin,
        )
        self.session.add(membership)
        await self.session.commit()
        return user

    async def _create_tags(self) -> list[Tag]:
        """Create demo tags."""
        tags = []
        for tag_data in DEMO_TAGS:
            tag = Tag(
                workspace_id=self.workspace_id,
                name=tag_data["name"],
                color=tag_data["color"],
            )
            self.session.add(tag)
            tags.append(tag)
        await self.session.flush()
        return tags

    async def _create_attribute_definitions(self) -> list[AttributeDefinition]:
        """Create demo attribute definitions."""
        definitions = []
        for attr_data in DEMO_ATTRIBUTE_DEFINITIONS:
            attr = AttributeDefinition(
                workspace_id=self.workspace_id,
                key=attr_data["key"],
                label=attr_data["label"],
                type=attr_data["type"],
                is_indexed=True,
            )
            self.session.add(attr)
            definitions.append(attr)
        await self.session.flush()
        self.attribute_definition_map = {
            definition.key: definition.id for definition in definitions
        }
        return definitions

    async def _create_contacts(self) -> list[Contact]:
        """Create demo contacts."""
        contacts = []
        contact_map = {}  # For conversation lookup

        for i, contact_data in enumerate(DEMO_CONTACTS):
            contact = Contact(
                workspace_id=self.workspace_id,
                name=contact_data["name"],
                phone=contact_data["phone"],
                tags=contact_data["tags"],
                status="active",
                created_at=datetime.now(
                    UTC) - timedelta(days=random.randint(1, 60)),
                last_activity_at=datetime.now(
                    UTC) - timedelta(days=random.randint(0, 7)),
            )
            self.session.add(contact)
            contacts.append(contact)
            contact_map[contact_data["phone"]] = contact

        await self.session.flush()

        # Create contact attributes
        for contact in contacts:
            company = random.choice(
                ["Acme Corp", "TechStart", "GlobalInc", "SmallBiz", "Enterprise Co", None])
            if company:
                definition_id = self.attribute_definition_map.get("company")
                if definition_id:
                    attr = ContactAttributeValue(
                        workspace_id=self.workspace_id,
                        contact_id=contact.id,
                        attribute_definition_id=definition_id,
                        value_text=company,
                    )
                    self.session.add(attr)

            employees = random.randint(
                1, 1000) if random.random() > 0.3 else None
            if employees:
                definition_id = self.attribute_definition_map.get("employees")
                if definition_id:
                    attr = ContactAttributeValue(
                        workspace_id=self.workspace_id,
                        contact_id=contact.id,
                        attribute_definition_id=definition_id,
                        value_number=employees,
                    )
                    self.session.add(attr)

            is_enterprise = random.random() > 0.8
            if is_enterprise:
                definition_id = self.attribute_definition_map.get(
                    "is_enterprise")
                if definition_id:
                    attr = ContactAttributeValue(
                        workspace_id=self.workspace_id,
                        contact_id=contact.id,
                        attribute_definition_id=definition_id,
                        value_bool=True,
                    )
                    self.session.add(attr)

        await self.session.commit()
        return contacts

    async def _create_segments(self) -> list[Segment]:
        """Create demo segments."""
        segments = []
        for seg_data in DEMO_SEGMENTS:
            segment = Segment(
                workspace_id=self.workspace_id,
                name=seg_data["name"],
                definition=seg_data["definition"],
                status="active",
                approx_size=random.randint(10, 25),
                last_materialized_at=datetime.now(
                    UTC) - timedelta(days=random.randint(0, 3)),
            )
            self.session.add(segment)
            segments.append(segment)
        await self.session.flush()
        await self.session.commit()
        return segments

    async def _create_templates(self) -> list[Template]:
        """Create demo templates."""
        templates = []
        for tmpl_data in DEMO_TEMPLATES:
            template = Template(
                workspace_id=self.workspace_id,
                name=tmpl_data["name"],
                content=tmpl_data["content"],
                status=TemplateStatus.APPROVED,
                category=tmpl_data["category"],
                language=tmpl_data["language"],
                header_type=tmpl_data.get("header_type", "none"),
                header_content=tmpl_data.get("header_content"),
                footer_text=tmpl_data.get("footer_text"),
                buttons=tmpl_data.get("buttons", []),
                created_by=self.user_id,
            )
            self.session.add(template)
            templates.append(template)
        await self.session.flush()
        await self.session.commit()
        return templates

    async def _create_campaigns(self, contacts: list[Contact]) -> list[Campaign]:
        """Create demo campaigns."""
        campaigns = []
        for camp_data in DEMO_CAMPAIGNS:
            scheduled = camp_data.get("scheduled_at")
            completed = camp_data.get("completed_at")

            campaign = Campaign(
                workspace_id=self.workspace_id,
                name=camp_data["name"],
                message_template=camp_data["message_template"],
                status=CampaignStatus(camp_data["status"]),
                scheduled_at=scheduled,
                completed_at=completed,
                created_by=self.user_id,
                sent_count=camp_data["stats"]["sent"],
                delivered_count=camp_data["stats"]["delivered"],
                read_count=camp_data["stats"]["read"],
                replied_count=camp_data["stats"]["replied"],
            )
            self.session.add(campaign)
            campaigns.append(campaign)
        await self.session.flush()
        await self.session.commit()
        return campaigns

    async def _create_workflows(self) -> list[WorkflowDefinition]:
        """Create demo workflows."""
        from app.models.workflow import WorkflowStatus
        workflows = []
        for wf_data in DEMO_WORKFLOWS:
            workflow = WorkflowDefinition(
                workspace_id=self.workspace_id,
                name=wf_data["name"],
                description=wf_data["description"],
                definition=wf_data["definition"],
                status=WorkflowStatus(wf_data["status"]),
                created_by=self.user_id,
            )
            self.session.add(workflow)
            workflows.append(workflow)
        await self.session.flush()
        await self.session.commit()
        return workflows

    async def _create_conversations(self, contacts: list[Contact]) -> tuple[int, int]:
        """Create demo conversations and messages."""
        from app.models.conversation import (
            ConversationStatus,
            ConversationChannel,
            MessageDirection,
            MessageSenderType,
            MessageContentType,
        )

        contact_map = {c.phone: c for c in contacts}
        conv_count = 0
        msg_count = 0

        # Group messages by phone
        conv_messages: dict[str, list[dict]] = {}
        for msg_data in DEMO_CONVERSATIONS:
            phone = msg_data["contact_phone"]
            if phone not in conv_messages:
                conv_messages[phone] = []
            conv_messages[phone].append(msg_data)

        for phone, messages in conv_messages.items():
            contact = contact_map.get(phone)
            if not contact:
                continue

            # Create conversation
            first_msg = messages[0]
            direction = MessageDirection.INBOUND if first_msg[
                "direction"] == "inbound" else MessageDirection.OUTBOUND

            conversation = Conversation(
                workspace_id=self.workspace_id,
                contact_id=contact.id,
                channel=ConversationChannel.whatsapp,
                status=ConversationStatus.OPEN,
                priority="normal",
                direction=direction,
                last_message_at=datetime.now(
                    UTC) - timedelta(minutes=random.randint(1, 60)),
            )
            self.session.add(conversation)
            await self.session.flush()
            conv_count += 1

            # Create messages
            msg_time = datetime.now(UTC) - timedelta(minutes=len(messages) * 5)
            for msg_data in messages:
                direction = MessageDirection.INBOUND if msg_data[
                    "direction"] == "inbound" else MessageDirection.OUTBOUND
                sender_type = MessageSenderType.CONTACT if msg_data[
                    "direction"] == "inbound" else MessageSenderType.AGENT

                message = ConversationMessage(
                    conversation_id=conversation.id,
                    workspace_id=self.workspace_id,
                    direction=direction,
                    sender_type=sender_type,
                    sender_id=self.user_id if msg_data["direction"] == "outbound" else None,
                    content_type=MessageContentType.text,
                    content=msg_data["content"],
                    created_at=msg_time,
                )
                self.session.add(message)
                msg_count += 1
                msg_time += timedelta(minutes=5)

        await self.session.commit()
        return conv_count, msg_count

    async def _create_activities(self, contacts: list[Contact]) -> None:
        """Create demo contact activities."""
        activity_types = [
            "created",
            "message_sent",
            "message_received",
            "tag_added",
            "campaign_started",
        ]

        for contact in contacts:
            # Create 3-8 activities per contact
            num_activities = random.randint(3, 8)
            for _ in range(num_activities):
                activity = ContactActivity(
                    workspace_id=self.workspace_id,
                    contact_id=contact.id,
                    type=random.choice(activity_types),
                    payload={"source": "bootstrap"},
                    actor_user_id=self.user_id,
                    created_at=datetime.now(
                        UTC) - timedelta(days=random.randint(0, 30)),
                )
                self.session.add(activity)

        await self.session.commit()


async def run_bootstrap(session: AsyncSession, reset: bool = False) -> dict[str, int]:
    """Run the bootstrap process."""
    bootstrapper = BootstrapService(session)
    return await bootstrapper.bootstrap(reset=reset)


async def ensure_bootstrap_admin(session: AsyncSession) -> User | None:
    """Ensure a bootstrap admin user exists for local development."""
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return None

    from app.services.auth_service import hash_password
    from app.services.user_service import create_user, get_user_by_email
    from app.services.workspace_service import (
        build_default_workspace_name,
        create_workspace_with_owner_membership,
    )
    from app.services.subscription_service import get_plan_by_name, upsert_user_subscription

    existing = await get_user_by_email(session, settings.bootstrap_admin_email)
    if existing:
        return existing

    user = await create_user(
        session=session,
        email=settings.bootstrap_admin_email,
        password_hash=hash_password(settings.bootstrap_admin_password),
        role=UserRole.super_admin,
        subscription_plan="free",
        is_active=True,
    )
    await create_workspace_with_owner_membership(
        session=session,
        name=build_default_workspace_name(user.email),
        owner_id=user.id,
    )

    plan = await get_plan_by_name(session=session, name="free")
    if plan is not None:
        await upsert_user_subscription(
            session=session,
            user_id=user.id,
            plan_id=plan.id,
        )

    return user
