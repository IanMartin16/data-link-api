from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import verify_api_key
from app.models.user import User
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
    Upgrades user to STARTER after successful Checkout completion.
    """

    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    if not signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        event = stripe_service.construct_webhook_event(payload, signature)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        metadata = session.get("metadata") or {}
        user_id = metadata.get("user_id")
        target_plan = metadata.get("target_plan")

        if user_id and target_plan == "STARTER":
            user = db.query(User).filter(User.id == user_id).first()

            if user:
                user.plan = "STARTER"
                user.stripe_customer_id = session.get("customer")
                user.stripe_subscription_id = session.get("subscription")
                user.billing_status = "active"
                db.commit()

    return {"received": True}