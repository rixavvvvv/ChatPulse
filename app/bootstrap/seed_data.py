"""Seed data for local development and testing."""

from datetime import UTC, datetime, timedelta
import random
from typing import Any

# Demo Workspace
DEMO_WORKSPACE = {
    "name": "ChatPulse Demo",
    "slug": "demo-workspace",
    "description": "Demo workspace for local development",
}

# Demo User
DEMO_USER = {
    "email": "admin@chatpulse.local",
    "password": "demo123",  # Will be hashed
    "full_name": "Demo Admin",
    "role": "admin",
}

# Demo Contacts (50 contacts)
DEMO_CONTACTS = [
    {"name": "Alice Johnson", "phone": "+14155551001", "tags": ["vip", "customer"]},
    {"name": "Bob Smith", "phone": "+14155551002", "tags": ["lead"]},
    {"name": "Charlie Brown", "phone": "+14155551003", "tags": ["customer"]},
    {"name": "Diana Prince", "phone": "+14155551004", "tags": ["vip"]},
    {"name": "Edward Norton", "phone": "+14155551005", "tags": ["lead", "prospect"]},
    {"name": "Fiona Apple", "phone": "+14155551006", "tags": ["customer"]},
    {"name": "George Miller", "phone": "+14155551007", "tags": []},
    {"name": "Hannah Montana", "phone": "+14155551008", "tags": ["vip", "customer"]},
    {"name": "Ian McKellen", "phone": "+14155551009", "tags": ["lead"]},
    {"name": "Julia Roberts", "phone": "+14155551010", "tags": ["customer"]},
    {"name": "Kevin Hart", "phone": "+14155551011", "tags": []},
    {"name": "Laura Palmer", "phone": "+14155551012", "tags": ["lead", "prospect"]},
    {"name": "Michael Scott", "phone": "+14155551013", "tags": ["vip"]},
    {"name": "Nina Simone", "phone": "+14155551014", "tags": ["customer"]},
    {"name": "Oscar Wilde", "phone": "+14155551015", "tags": ["lead"]},
    {"name": "Patricia Arquette", "phone": "+14155551016", "tags": ["customer"]},
    {"name": "Quincy Jones", "phone": "+14155551017", "tags": ["vip", "mentor"]},
    {"name": "Rachel Green", "phone": "+14155551018", "tags": ["customer"]},
    {"name": "Steve Rogers", "phone": "+14155551019", "tags": ["lead"]},
    {"name": "Tina Turner", "phone": "+14155551020", "tags": ["vip"]},
    {"name": "Uma Thurman", "phone": "+14155551021", "tags": ["customer"]},
    {"name": "Victor Hugo", "phone": "+14155551022", "tags": ["lead", "writer"]},
    {"name": "Wendy Williams", "phone": "+14155551023", "tags": ["customer"]},
    {"name": "Xavier Naidoo", "phone": "+14155551024", "tags": []},
    {"name": "Yolanda Adams", "phone": "+14155551025", "tags": ["vip", "singer"]},
    {"name": "Zack Morris", "phone": "+14155551026", "tags": ["lead"]},
    {"name": "Amy Adams", "phone": "+14155551027", "tags": ["customer"]},
    {"name": "Brad Pitt", "phone": "+14155551028", "tags": ["vip"]},
    {"name": "Chris Evans", "phone": "+14155551029", "tags": ["lead"]},
    {"name": "Emma Watson", "phone": "+14155551030", "tags": ["customer", "vip"]},
    {"name": "Frank Ocean", "phone": "+14155551031", "tags": ["lead"]},
    {"name": "Grace Kelly", "phone": "+14155551032", "tags": ["vip"]},
    {"name": "Henry Cavill", "phone": "+14155551033", "tags": ["customer"]},
    {"name": "Iris Van Der", "phone": "+14155551034", "tags": ["lead", "fashion"]},
    {"name": "Jack Black", "phone": "+14155551035", "tags": ["customer"]},
    {"name": "Kate Winslet", "phone": "+14155551036", "tags": ["vip"]},
    {"name": "Leonardo DiCaprio", "phone": "+14155551037", "tags": ["lead"]},
    {"name": "Margot Robbie", "phone": "+14155551038", "tags": ["customer"]},
    {"name": "Natalie Portman", "phone": "+14155551039", "tags": ["vip", "actor"]},
    {"name": "Orlando Bloom", "phone": "+14155551040", "tags": ["lead"]},
    {"name": "Penelope Cruz", "phone": "+14155551041", "tags": ["customer"]},
    {"name": "Robert Downey", "phone": "+14155551042", "tags": ["vip"]},
    {"name": "Scarlett Johansson", "phone": "+14155551043", "tags": ["customer"]},
    {"name": "Tom Hanks", "phone": "+14155551044", "tags": ["lead", "vip"]},
    {"name": "Ursula Burns", "phone": "+14155551045", "tags": ["customer"]},
    {"name": "Vin Diesel", "phone": "+14155551046", "tags": ["lead"]},
    {"name": "Will Smith", "phone": "+14155551047", "tags": ["vip", "actor"]},
    {"name": "Xena Warrior", "phone": "+14155551048", "tags": ["lead"]},
    {"name": "Yvonne Strahovski", "phone": "+14155551049", "tags": ["customer"]},
    {"name": "Zoe Saldana", "phone": "+14155551050", "tags": ["vip"]},
]

# Demo Tags
DEMO_TAGS = [
    {"name": "vip", "color": "#FFD700"},
    {"name": "customer", "color": "#4CAF50"},
    {"name": "lead", "color": "#2196F3"},
    {"name": "prospect", "color": "#9C27B0"},
    {"name": "partner", "color": "#FF9800"},
    {"name": "inactive", "color": "#9E9E9E"},
]

# Demo Contact Attributes
DEMO_ATTRIBUTE_DEFINITIONS = [
    {"key": "company", "label": "Company", "type": "text"},
    {"key": "industry", "label": "Industry", "type": "text"},
    {"key": "employees", "label": "Employees", "type": "number"},
    {"key": "annual_revenue", "label": "Annual Revenue", "type": "number"},
    {"key": "is_enterprise", "label": "Enterprise", "type": "boolean"},
    {"key": "signup_date", "label": "Signup Date", "type": "date"},
    {"key": "last_purchase", "label": "Last Purchase", "type": "date"},
    {"key": "lifetime_value", "label": "Lifetime Value", "type": "number"},
]

# Demo Segments
DEMO_SEGMENTS = [
    {
        "name": "VIP Customers",
        "definition": {
            "op": "and",
            "children": [
                {"op": "has_tag", "tag": "vip"},
                {"op": "has_tag", "tag": "customer"},
            ],
        },
    },
    {
        "name": "Active Leads",
        "definition": {
            "op": "and",
            "children": [
                {"op": "has_tag", "tag": "lead"},
            ],
        },
    },
    {
        "name": "Prospects",
        "definition": {
            "op": "and",
            "children": [
                {"op": "has_tag", "tag": "prospect"},
            ],
        },
    },
]

# Demo Templates
DEMO_TEMPLATES = [
    {
        "name": "Welcome Message",
        "content": "Hello {{name}}! Welcome to ChatPulse. We're excited to have you on board!",
        "category": "MARKETING",
        "language": "en_US",
        "header_type": "text",
        "header_content": "Welcome!",
        "footer_text": "Reply STOP to unsubscribe",
        "buttons": [],
    },
    {
        "name": "Order Confirmation",
        "content": "Hi {{name}}, your order #{{order_id}} has been confirmed! We'll notify you when it ships.",
        "category": "TRANSACTIONAL",
        "language": "en_US",
        "header_type": "text",
        "header_content": "Order Confirmed",
        "footer_text": "",
        "buttons": [
            {"type": "URL", "text": "Track Order", "url": "https://example.com/track/{{order_id}}"},
        ],
    },
    {
        "name": "Promo Announcement",
        "content": "Hi {{name}}! 🎉 Don't miss our {{promo_name}} - {{discount}}% off! Valid until {{end_date}}.",
        "category": "MARKETING",
        "language": "en_US",
        "header_type": "text",
        "header_content": "Special Offer!",
        "footer_text": "Limited time only",
        "buttons": [
            {"type": "QUICK_REPLY", "text": "Claim Now"},
            {"type": "QUICK_REPLY", "text": "No Thanks"},
        ],
    },
    {
        "name": "Appointment Reminder",
        "content": "Reminder: You have an appointment on {{date}} at {{time}}. Reply C to confirm or R to reschedule.",
        "category": "APPOINTMENT",
        "language": "en_US",
        "header_type": "text",
        "header_content": "Appointment Reminder",
        "footer_text": "",
        "buttons": [
            {"type": "QUICK_REPLY", "text": "Confirm"},
            {"type": "QUICK_REPLY", "text": "Reschedule"},
        ],
    },
    {
        "name": "Feedback Request",
        "content": "Hi {{name}}, thanks for your recent purchase! How was your experience? Rate us: {{rating_url}}",
        "category": "MARKETING",
        "language": "en_US",
        "header_type": "text",
        "header_content": "Feedback",
        "footer_text": "It only takes 1 minute",
        "buttons": [
            {"type": "URL", "text": "Leave Review", "url": "{{rating_url}}"},
        ],
    },
]

# Demo Campaigns
DEMO_CAMPAIGNS = [
    {
        "name": "Summer Sale 2024",
        "status": "completed",
        "message_template": "Hi {{name}}! ☀️ Summer Sale - Get 30% off all items! Use code SUMMER30. Offer valid until July 31st!",
        "contact_tags": ["customer", "lead"],
        "scheduled_at": datetime.now(UTC) - timedelta(days=7),
        "completed_at": datetime.now(UTC) - timedelta(days=6),
        "stats": {"sent": 35, "delivered": 33, "read": 28, "replied": 5},
    },
    {
        "name": "New Product Launch",
        "status": "completed",
        "message_template": "Hi {{name}}! 🚀 Introducing our new AI-powered features! Get early access: {{link}}",
        "contact_tags": ["vip", "customer"],
        "scheduled_at": datetime.now(UTC) - timedelta(days=3),
        "completed_at": datetime.now(UTC) - timedelta(days=2),
        "stats": {"sent": 20, "delivered": 19, "read": 17, "replied": 8},
    },
    {
        "name": "Weekly Newsletter",
        "status": "scheduled",
        "message_template": "Hi {{name}}! 📰 This week's highlights: New features, tips & tricks, and community updates!",
        "contact_tags": [],
        "scheduled_at": datetime.now(UTC) + timedelta(days=2),
        "completed_at": None,
        "stats": {"sent": 0, "delivered": 0, "read": 0, "replied": 0},
    },
    {
        "name": "Customer Feedback Survey",
        "status": "draft",
        "message_template": "Hi {{name}}, we'd love your feedback! Take our 2-min survey: {{survey_link}}",
        "contact_tags": ["customer"],
        "scheduled_at": None,
        "completed_at": None,
        "stats": {"sent": 0, "delivered": 0, "read": 0, "replied": 0},
    },
    {
        "name": "Cart Abandonment Reminder",
        "status": "active",
        "message_template": "Hi {{name}}! You left items in your cart. Complete your purchase now and get free shipping!",
        "contact_tags": ["prospect"],
        "scheduled_at": None,
        "completed_at": None,
        "stats": {"sent": 15, "delivered": 14, "read": 10, "replied": 2},
    },
]

# Demo Conversations (sample)
DEMO_CONVERSATIONS = [
    {"contact_phone": "+14155551001", "direction": "inbound", "content": "Hi, I'm interested in your product!"},
    {"contact_phone": "+14155551001", "direction": "outbound", "content": "Hello Alice! Thank you for reaching out. How can I help you today?"},
    {"contact_phone": "+14155551001", "direction": "inbound", "content": "Can you tell me more about the pricing plans?"},
    {"contact_phone": "+14155551001", "direction": "outbound", "content": "Sure! We have Free ($0), Pro ($29), Business ($99), and Enterprise ($299) plans. Which one interests you?"},
    {"contact_phone": "+14155551002", "direction": "inbound", "content": "I want to schedule a demo"},
    {"contact_phone": "+14155551002", "direction": "outbound", "content": "I'd be happy to help schedule a demo! What date and time works for you?"},
    {"contact_phone": "+14155551003", "direction": "inbound", "content": "Is there a student discount?"},
    {"contact_phone": "+14155551003", "direction": "outbound", "content": "Yes! We offer 50% off for students and educators. Would you like me to send you the discount code?"},
    {"contact_phone": "+14155551004", "direction": "inbound", "content": "The product is amazing! Thanks!"},
    {"contact_phone": "+14155551004", "direction": "outbound", "content": "Thank you so much, Diana! We're thrilled you're enjoying it. Let us know if you need anything else!"},
    {"contact_phone": "+14155551005", "direction": "inbound", "content": "How do I integrate with your API?"},
    {"contact_phone": "+14155551005", "direction": "outbound", "content": "Great question! You can find our API documentation at docs.chatpulse.io. We also have SDKs for Python, Node, and Go."},
    {"contact_phone": "+14155551006", "direction": "inbound", "content": "Can I upgrade my plan?"},
    {"contact_phone": "+14155551006", "direction": "outbound", "content": "Absolutely! You can upgrade anytime from Settings > Billing. Would you like me to highlight the Pro features?"},
]

# Demo Workflows (using WorkflowDefinition)
DEMO_WORKFLOWS = [
    {
        "name": "Welcome Series",
        "description": "Welcome new contacts with a 3-message sequence",
        "definition": {
            "nodes": [
                {"id": "1", "type": "trigger", "data": {"event": "contact_created"}},
                {"id": "2", "type": "action", "data": {"action": "send_message", "template": "Welcome Message"}},
                {"id": "3", "type": "delay", "data": {"duration": 1, "unit": "day"}},
                {"id": "4", "type": "action", "data": {"action": "send_message", "template": "Feedback Request"}},
                {"id": "5", "type": "end", "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "1", "target": "2"},
                {"id": "e2", "source": "2", "target": "3"},
                {"id": "e3", "source": "3", "target": "4"},
                {"id": "e4", "source": "4", "target": "5"},
            ],
        },
        "status": "published",
    },
    {
        "name": "Cart Abandonment",
        "description": "Remind customers about items in their cart",
        "definition": {
            "nodes": [
                {"id": "1", "type": "trigger", "data": {"event": "cart_abandoned"}},
                {"id": "2", "type": "action", "data": {"action": "send_message", "template": "Cart Abandonment Reminder"}},
                {"id": "3", "type": "delay", "data": {"duration": 2, "unit": "hour"}},
                {"id": "4", "type": "action", "data": {"action": "send_message", "content": "Hi! Just checking if you need help completing your order? 🎁"}},
                {"id": "5", "type": "end", "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "1", "target": "2"},
                {"id": "e2", "source": "2", "target": "3"},
                {"id": "e3", "source": "3", "target": "4"},
                {"id": "e4", "source": "4", "target": "5"},
            ],
        },
        "status": "published",
    },
    {
        "name": "Lead Nurturing",
        "description": "Nurture leads over 7 days",
        "definition": {
            "nodes": [
                {"id": "1", "type": "trigger", "data": {"event": "tag_added", "tag": "lead"}},
                {"id": "2", "type": "action", "data": {"action": "send_message", "content": "Thanks for your interest! Here's our product overview: {{product_link}}"}},
                {"id": "3", "type": "delay", "data": {"duration": 2, "unit": "day"}},
                {"id": "4", "type": "action", "data": {"action": "send_message", "content": "Have questions? Reply to this message - we're here to help!"}},
                {"id": "5", "type": "delay", "data": {"duration": 3, "unit": "day"}},
                {"id": "6", "type": "action", "data": {"action": "send_message", "content": "Last chance! Our special offer ends in 24 hours. Use code LEAD20 for 20% off."}},
                {"id": "7", "type": "end", "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "1", "target": "2"},
                {"id": "e2", "source": "2", "target": "3"},
                {"id": "e3", "source": "3", "target": "4"},
                {"id": "e4", "source": "4", "target": "5"},
                {"id": "e5", "source": "5", "target": "6"},
                {"id": "e6", "source": "6", "target": "7"},
            ],
        },
        "status": "draft",
    },
    {
        "name": "Support Ticket",
        "description": "Auto-respond to support requests",
        "definition": {
            "nodes": [
                {"id": "1", "type": "trigger", "data": {"event": "keyword", "keyword": "help"}},
                {"id": "2", "type": "action", "data": {"action": "send_message", "content": "Thanks for reaching out! A support agent will be with you shortly. For immediate help, visit our help center: {{help_link}}"}},
                {"id": "3", "type": "end", "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "1", "target": "2"},
                {"id": "e2", "source": "2", "target": "3"},
            ],
        },
        "status": "published",
    },
]

# Demo Analytics Data
def generate_demo_analytics() -> list[dict[str, Any]]:
    """Generate fake analytics data for the past 30 days."""
    analytics = []
    base_date = datetime.now(UTC).date()

    for i in range(30):
        date = base_date - timedelta(days=i)
        # Random but somewhat realistic numbers
        messages_sent = random.randint(50, 200)
        messages_delivered = int(messages_sent * random.uniform(0.95, 0.99))
        messages_read = int(messages_delivered * random.uniform(0.6, 0.85))
        messages_replied = int(messages_read * random.uniform(0.1, 0.3))
        new_contacts = random.randint(5, 25)
        active_contacts = random.randint(100, 300)
        conversations = random.randint(20, 80)
        campaigns_sent = random.randint(1, 5)

        analytics.append({
            "date": date.isoformat(),
            "messages_sent": messages_sent,
            "messages_delivered": messages_delivered,
            "messages_read": messages_read,
            "messages_replied": messages_replied,
            "new_contacts": new_contacts,
            "active_contacts": active_contacts,
            "conversations": conversations,
            "campaigns_sent": campaigns_sent,
            "revenue": random.uniform(100, 500),
        })

    return analytics


# Demo Message Events
DEMO_MESSAGE_EVENTS = [
    {"event": "sent", "count": 150},
    {"event": "delivered", "count": 145},
    {"event": "read", "count": 120},
    {"event": "replied", "count": 35},
    {"event": "failed", "count": 5},
]

# Demo Contact Activity Types
DEMO_ACTIVITY_TYPES = [
    "created",
    "message_sent",
    "message_received",
    "tag_added",
    "tag_removed",
    "segment_updated",
    "campaign_started",
    "campaign_completed",
    "workflow_triggered",
]