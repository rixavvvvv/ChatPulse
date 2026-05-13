"""
Ecommerce Workflow Templates

Pre-built automation configurations for common ecommerce workflows.
These serve as templates that can be instantiated by the user.
"""

from typing import Any


def get_all_templates() -> list[dict[str, Any]]:
    """Return all available ecommerce automation templates."""
    return [
        abandoned_cart_1h(),
        abandoned_cart_24h(),
        order_confirmation_immediate(),
        shipment_created_notification(),
        shipment_delivered_notification(),
        cod_verification_24h(),
        post_purchase_followup_7d(),
        review_request_14d(),
    ]


def abandoned_cart_1h() -> dict[str, Any]:
    """Abandoned cart recovery — 1 hour delay."""
    return {
        "template_key": "abandoned_cart_1h",
        "name": "Abandoned Cart Recovery (1 Hour)",
        "description": "Send a cart recovery reminder 1 hour after the customer abandons their cart.",
        "automation_type": "abandoned_cart_recovery",
        "trigger_config": {
            "trigger_type": "cart_abandoned",
            "config": {
                "cart_idle_minutes": 60,
                "recovery_window_hours": 72,
                "include_abandoned_items": True,
            },
        },
        "action_config": {
            "action_type": "send_template_message",
            "template_id": None,  # User must select
            "fallback_message": None,
        },
        "delay_seconds": 3600,
        "delay_type": "fixed",
        "priority": 10,
        "max_retries": 3,
    }


def abandoned_cart_24h() -> dict[str, Any]:
    """Abandoned cart recovery — 24 hour delay (follow-up)."""
    return {
        "template_key": "abandoned_cart_24h",
        "name": "Abandoned Cart Recovery (24 Hours)",
        "description": "Send a second cart recovery reminder 24 hours after abandonment.",
        "automation_type": "abandoned_cart_recovery",
        "trigger_config": {
            "trigger_type": "cart_abandoned",
            "config": {
                "cart_idle_minutes": 1440,
                "recovery_window_hours": 72,
                "include_abandoned_items": True,
            },
        },
        "action_config": {
            "action_type": "send_template_message",
            "template_id": None,
            "fallback_message": None,
        },
        "delay_seconds": 86400,
        "delay_type": "fixed",
        "priority": 5,
        "max_retries": 3,
    }


def order_confirmation_immediate() -> dict[str, Any]:
    """Order confirmation — send immediately on order creation."""
    return {
        "template_key": "order_confirmation_immediate",
        "name": "Order Confirmation",
        "description": "Send an instant order confirmation with order details.",
        "automation_type": "order_confirmation",
        "trigger_config": {
            "trigger_type": "order_created",
            "config": {
                "send_immediately": True,
                "include_order_details": True,
                "include_estimated_delivery": True,
                "attach_invoice": False,
            },
        },
        "action_config": {
            "action_type": "send_template_message",
            "template_id": None,
            "fallback_message": None,
        },
        "delay_seconds": 0,
        "delay_type": None,
        "priority": 20,
        "max_retries": 3,
    }


def shipment_created_notification() -> dict[str, Any]:
    """Shipment created — notify customer when order is shipped."""
    return {
        "template_key": "shipment_created",
        "name": "Shipment Created Notification",
        "description": "Notify customer when their order has been shipped with tracking details.",
        "automation_type": "shipment_updates",
        "trigger_config": {
            "trigger_type": "shipment_created",
            "config": {
                "notify_on": ["created"],
                "include_tracking_link": True,
                "carrier_name_field": "carrier",
            },
        },
        "action_config": {
            "action_type": "send_template_message",
            "template_id": None,
            "fallback_message": None,
        },
        "delay_seconds": 0,
        "delay_type": None,
        "priority": 15,
        "max_retries": 3,
    }


def shipment_delivered_notification() -> dict[str, Any]:
    """Shipment delivered — notify customer on delivery."""
    return {
        "template_key": "shipment_delivered",
        "name": "Delivery Confirmation",
        "description": "Notify customer when their order has been delivered.",
        "automation_type": "delivered_notifications",
        "trigger_config": {
            "trigger_type": "shipment_delivered",
            "config": {
                "notify_on": ["delivered"],
                "include_tracking_link": False,
            },
        },
        "action_config": {
            "action_type": "send_template_message",
            "template_id": None,
            "fallback_message": None,
        },
        "delay_seconds": 0,
        "delay_type": None,
        "priority": 15,
        "max_retries": 3,
    }


def cod_verification_24h() -> dict[str, Any]:
    """COD verification — send reminder after 24 hours."""
    return {
        "template_key": "cod_verification_24h",
        "name": "COD Payment Verification",
        "description": "Send a COD payment verification reminder 24 hours after order placement.",
        "automation_type": "cod_verification",
        "trigger_config": {
            "trigger_type": "cod_pending",
            "config": {
                "verification_window_hours": 24,
                "reminder_after_hours": 12,
                "max_reminders": 2,
            },
        },
        "action_config": {
            "action_type": "send_template_message",
            "template_id": None,
            "fallback_message": None,
        },
        "delay_seconds": 43200,  # 12 hours
        "delay_type": "fixed",
        "priority": 10,
        "max_retries": 2,
    }


def post_purchase_followup_7d() -> dict[str, Any]:
    """Post-purchase follow-up — 7 days after delivery."""
    return {
        "template_key": "post_purchase_followup_7d",
        "name": "Post-Purchase Follow-up (7 Days)",
        "description": "Send a follow-up message 7 days after delivery to check satisfaction.",
        "automation_type": "post_purchase_followup",
        "trigger_config": {
            "trigger_type": "shipment_delivered",
            "config": {},
        },
        "action_config": {
            "action_type": "send_template_message",
            "template_id": None,
            "fallback_message": None,
        },
        "delay_seconds": 604800,  # 7 days
        "delay_type": "fixed",
        "priority": 1,
        "max_retries": 2,
    }


def review_request_14d() -> dict[str, Any]:
    """Review request — 14 days after delivery."""
    return {
        "template_key": "review_request_14d",
        "name": "Review Request (14 Days)",
        "description": "Request a product review 14 days after delivery.",
        "automation_type": "review_request",
        "trigger_config": {
            "trigger_type": "shipment_delivered",
            "config": {},
        },
        "action_config": {
            "action_type": "send_template_message",
            "template_id": None,
            "fallback_message": None,
        },
        "delay_seconds": 1209600,  # 14 days
        "delay_type": "fixed",
        "priority": 0,
        "max_retries": 1,
    }


def get_template_by_key(key: str) -> dict[str, Any] | None:
    """Get a specific template by its key."""
    templates = {t["template_key"]: t for t in get_all_templates()}
    return templates.get(key)
