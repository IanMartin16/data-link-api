import stripe

from app.config import get_settings

settings = get_settings()

if settings.stripe_secret_key:
    stripe.api_key = settings.stripe_secret_key


class StripeService:
    def create_starter_checkout_session(self, user):
        """
        Create a Stripe Checkout session for STARTER subscription.
        """

        if not settings.stripe_secret_key:
            raise RuntimeError("STRIPE_SECRET_KEY is not configured.")

        if not settings.stripe_starter_price_id:
            raise RuntimeError("STRIPE_STARTER_PRICE_ID is not configured.")

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=user.email,
            line_items=[
                {
                    "price": settings.stripe_starter_price_id,
                    "quantity": 1,
                }
            ],
            success_url=settings.billing_success_url,
            cancel_url=settings.billing_cancel_url,
            client_reference_id=str(user.id),
            metadata={
                "user_id": str(user.id),
                "target_plan": "STARTER",
                "product": "data_link",
            },
        )

        return session

    def construct_webhook_event(self, payload: bytes, signature: str):
        """
        Validate and construct Stripe webhook event.
        """

        if not settings.stripe_webhook_secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured.")

        return stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=settings.stripe_webhook_secret,
        )


stripe_service = StripeService()