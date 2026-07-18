from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import verify_api_key
from app.models.user import User
from datetime import datetime, timezone
from app.services.stripe_service import stripe_service

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.post("/create-checkout-session")
async def create_checkout_session(
    user: User = Depends(verify_api_key),
):
    """
    Create a Stripe Checkout session to upgrade current user to STARTER.
    """

    if user.plan == "STARTER":
        return {
            "message": "User is already on STARTER plan.",
            "checkout_url": None
        }

    try:
        session = stripe_service.create_starter_checkout_session(user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "checkout_url": session.url
    }


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Stripe webhook endpoint.

    Rules:
    - Valid Stripe signature is required.
    - Data_Link product_id + price_id are required before granting STARTER.
    - Foreign Evilink products return 200 ignored.
    """

    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    if not signature:
        raise HTTPException(
            status_code=400,
            detail="Missing Stripe signature",
        )

    try:
        event = stripe_service.construct_webhook_event(
            payload,
            signature,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event["type"]

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]

        metadata = session.get("metadata") or {}
        user_id = metadata.get("user_id") or session.get("client_reference_id")
        subscription_id = session.get("subscription")
        customer_id = session.get("customer")

        if not user_id or not subscription_id:
            raise HTTPException(
                status_code=500,
                detail="Missing user_id or subscription_id",
            )

        subscription = stripe_service.retrieve_subscription_expanded(
            subscription_id,
        )

        ownership = stripe_service.classify_datalink_subscription(
            subscription,
        )

        if ownership["type"] == "foreign":
            return {
                "received": True,
                "ignored": True,
                "reason": "wrong_product",
                "event_type": event_type,
                "product_id": ownership["product_id"],
                "price_id": ownership["price_id"],
            }

        if ownership["type"] == "invalid":
            raise HTTPException(
                status_code=500,
                detail="Unable to determine Stripe product identity",
            )

        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(
                status_code=500,
                detail="User not found for checkout session",
            )

        user.plan = "STARTER"
        user.stripe_customer_id = customer_id
        user.stripe_subscription_id = subscription_id
        user.stripe_product_id = ownership["product_id"]
        user.stripe_price_id = ownership["price_id"]
        user.billing_status = subscription.get("status") or "active"
        user.cancellation_scheduled = False
        user.stripe_cancel_at = None
        user.current_period_end = stripe_service.resolve_current_period_end(
            subscription,
        )
        user.revoked_at = None

        db.commit()

        return {
            "received": True,
            "processed": True,
            "event_type": event_type,
        }

    if event_type == "customer.subscription.updated":
        subscription_event = event["data"]["object"]
        subscription_id = subscription_event.get("id")

        if not subscription_id:
            raise HTTPException(
                status_code=500,
                detail="Missing subscription id",
            )

        subscription = stripe_service.retrieve_subscription_expanded(
            subscription_id,
        )

        ownership = stripe_service.classify_datalink_subscription(
            subscription,
        )

        if ownership["type"] == "foreign":
            return {
                "received": True,
                "ignored": True,
                "reason": "wrong_product",
                "event_type": event_type,
                "product_id": ownership["product_id"],
                "price_id": ownership["price_id"],
            }

        if ownership["type"] == "invalid":
            raise HTTPException(
                status_code=500,
                detail="Unable to determine Stripe product identity",
            )

        user = db.query(User).filter(
            User.stripe_subscription_id == subscription_id
        ).first()

        if not user:
            raise HTTPException(
                status_code=500,
                detail="No user found for subscription",
            )

        subscription_status = subscription.get("status")

        cancel_at_period_end = bool(
            subscription.get("cancel_at_period_end")
        )

        stripe_cancel_at = stripe_service.epoch_to_datetime(
            subscription.get("cancel_at")
        )

        current_period_end = stripe_service.resolve_current_period_end(
            subscription,
        )

        cancellation_scheduled = (
            cancel_at_period_end or stripe_cancel_at is not None
        )

        should_remain_starter = subscription_status in {
            "active",
            "trialing",
            "past_due",
        }

        user.billing_status = subscription_status
        user.stripe_product_id = ownership["product_id"]
        user.stripe_price_id = ownership["price_id"]
        user.cancellation_scheduled = cancellation_scheduled
        user.stripe_cancel_at = stripe_cancel_at
        user.current_period_end = current_period_end

        if should_remain_starter:
            user.plan = "STARTER"
            user.revoked_at = None
        else:
            user.plan = "FREE"
            user.revoked_at = datetime.now(timezone.utc)

        db.commit()

        return {
            "received": True,
            "processed": True,
            "event_type": event_type,
            "subscription_status": subscription_status,
            "cancellation_scheduled": cancellation_scheduled,
        }

    if event_type == "customer.subscription.deleted":
        subscription_event = event["data"]["object"]
        subscription_id = subscription_event.get("id")

        if not subscription_id:
            raise HTTPException(
                status_code=500,
                detail="Missing subscription id",
            )

        subscription = stripe_service.retrieve_subscription_expanded(
            subscription_id,
        )

        ownership = stripe_service.classify_datalink_subscription(
            subscription,
        )

        if ownership["type"] == "foreign":
            return {
                "received": True,
                "ignored": True,
                "reason": "wrong_product",
                "event_type": event_type,
                "product_id": ownership["product_id"],
                "price_id": ownership["price_id"],
            }

        if ownership["type"] == "invalid":
            raise HTTPException(
                status_code=500,
                detail="Unable to determine Stripe product identity",
            )

        user = db.query(User).filter(
            User.stripe_subscription_id == subscription_id
        ).first()

        if not user:
            raise HTTPException(
                status_code=500,
                detail="No user found for deleted subscription",
            )

        user.plan = "FREE"
        user.billing_status = "canceled"
        user.cancellation_scheduled = False
        user.stripe_cancel_at = None
        user.revoked_at = datetime.now(timezone.utc)

        db.commit()

        return {
            "received": True,
            "processed": True,
            "event_type": event_type,
        }

    return {
        "received": True,
        "ignored": True,
        "event_type": event_type,
    }

@router.post("/portal-session")
async def create_billing_portal_session(
    user: User = Depends(verify_api_key),
):
    """
    Create a Stripe Billing Portal session for the current user.
    """

    if not user.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="User does not have an active Stripe customer.",
        )

    if not user.stripe_subscription_id:
        raise HTTPException(
            status_code=400,
            detail="User does not have an active Stripe subscription.",
        )

    try:
        session = stripe_service.create_billing_portal_session(user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "portal_url": session.url,
    }