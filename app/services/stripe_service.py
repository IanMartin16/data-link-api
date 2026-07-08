import stripe

from datetime import datetime, timezone
from app.config import get_settings

settings = get_settings()

if settings.stripe_secret_key:
    stripe.api_key = settings.stripe_secret_key


class StripeService:
    def create_starter_checkout_session(self, user):
        """
        Create a Stripe Checkout session for STARTER subscription.
        """

        self._ensure_checkout_config()

        session_params = {
            "mode": "subscription",
            "line_items": [
                {
                    "price": settings.stripe_starter_price_id,
                    "quantity": 1,
                }
            ],
            "success_url": settings.billing_success_url,
            "cancel_url": settings.billing_cancel_url,
            "client_reference_id": str(user.id),
            "metadata": {
                "user_id": str(user.id),
                "target_plan": "STARTER",
                "product": "data_link",
            },
        }

        if user.stripe_customer_id:
            session_params["customer"] = user.stripe_customer_id
        else:
            session_params["customer_email"] = user.email

        return stripe.checkout.Session.create(**session_params)

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

    def retrieve_subscription_expanded(self, subscription_id: str):
        if not settings.stripe_secret_key:
            raise RuntimeError("STRIPE_SECRET_KEY is not configured.")

        if not subscription_id:
            raise RuntimeError("subscription_id is required.")

        return stripe.Subscription.retrieve(
            subscription_id,
            expand=["items.data.price.product"],
        )

    def classify_datalink_subscription(self, subscription):
        """
        Classify whether a Stripe subscription belongs to Data_Link.

        Returns:
        {
          "type": "datalink" | "foreign" | "invalid",
          "product_id": str | None,
          "price_id": str | None,
          "plan": "STARTER" | None
        }
        """

        product_id_expected = getattr(
            settings,
            "datalink_stripe_product_id",
            None,
        )

        price_id_expected = settings.stripe_starter_price_id

        if not product_id_expected or not price_id_expected:
            return {
                "type": "invalid",
                "product_id": None,
                "price_id": None,
                "plan": None,
            }

        item = self._first_subscription_item(subscription)

        if not item:
            return {
                "type": "invalid",
                "product_id": None,
                "price_id": None,
                "plan": None,
            }

        price = item.get("price") if hasattr(item, "get") else None

        if not price:
            return {
                "type": "invalid",
                "product_id": None,
                "price_id": None,
                "plan": None,
            }

        price_id = price.get("id")
        product_id = self.stripe_object_id(price.get("product"))

        if not price_id or not product_id:
            return {
                "type": "invalid",
                "product_id": product_id,
                "price_id": price_id,
                "plan": None,
            }

        belongs_to_datalink = (
            product_id == product_id_expected
            and price_id == price_id_expected
        )

        if not belongs_to_datalink:
            return {
                "type": "foreign",
                "product_id": product_id,
                "price_id": price_id,
                "plan": None,
            }

        return {
            "type": "datalink",
            "product_id": product_id,
            "price_id": price_id,
            "plan": "STARTER",
        }

    def resolve_current_period_end(self, subscription):
        root_value = subscription.get("current_period_end")

        if root_value:
            return self.epoch_to_datetime(root_value)

        item = self._first_subscription_item(subscription)

        if not item:
            return None

        item_value = item.get("current_period_end")

        if not item_value:
            return None

        return self.epoch_to_datetime(item_value)

    def epoch_to_datetime(self, value):
        if not value:
            return None

        return datetime.fromtimestamp(
            int(value),
            tz=timezone.utc,
        )

    def stripe_object_id(self, value):
        if not value:
            return None

        if isinstance(value, str):
            return value

        if hasattr(value, "get"):
            return value.get("id")

        return getattr(value, "id", None)

    def _first_subscription_item(self, subscription):
        items = subscription.get("items")

        if not items:
            return None

        data = items.get("data") or []

        if not data:
            return None

        return data[0]

    def _ensure_checkout_config(self):
        if not settings.stripe_secret_key:
            raise RuntimeError("STRIPE_SECRET_KEY is not configured.")

        if not settings.stripe_starter_price_id:
            raise RuntimeError("STRIPE_STARTER_PRICE_ID is not configured.")

        product_id = getattr(
            settings,
            "datalink_stripe_product_id",
            None,
        )

        if not product_id:
            raise RuntimeError("DATALINK_STRIPE_PRODUCT_ID is not configured.")


stripe_service = StripeService()