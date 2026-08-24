import logging
from typing import Any

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from config import settings

from ..models import (
    CheckoutSession,
    Payment,
    Product,
    Provider,
    Subscription,
    WebhookEvent,
)
from .stripe import (
    stripe_datetime,
    sync_invoice,
    sync_subscription,
)

logger = logging.getLogger(__name__)


def process_webhook(
    event: dict[str, Any],
) -> None:

    event_id = str(
        event.get("id") or ""
    )

    event_type = str(
        event.get("type") or ""
    )

    data = (
        event.get("data", {})
        .get("object", {})
    )

    logger.info(
        "Processing Stripe event "
        "id=%s type=%s",
        event_id,
        event_type,
    )

    # ========================================================
    # Checkout
    # ========================================================

    if event_type == "checkout.session.completed":

        session = (
            CheckoutSession.objects
            .filter(
                provider=Provider.STRIPE,
                provider_session_id=data.get("id"),
            )
            .first()
        )

        if session:
            session.status = (
                data.get("status")
                or "complete"
            )

            session.completed_at = (
                session.completed_at
                or timezone.now()
            )

            session.metadata = (
                data.get("metadata")
                or session.metadata
                or {}
            )

            session.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "metadata",
                ]
            )

        return

    # ========================================================
    # Subscription
    # ========================================================

    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
    }:
        sync_subscription(data)
        return

    # ========================================================
    # Subscription deleted
    # ========================================================

    if event_type == "customer.subscription.deleted":

        subscription = (
            Subscription.objects
            .filter(
                provider=Provider.STRIPE,
                provider_subscription_id=data.get("id"),
            )
            .first()
        )

        if subscription:
            subscription.status = (
                Subscription.Status.CANCELED
            )

            subscription.cancel_at_period_end = False

            subscription.canceled_at = (
                subscription.canceled_at
                or timezone.now()
            )

            subscription.save()

        return

    # ========================================================
    # Invoice
    # ========================================================

    if event_type.startswith("invoice."):

        invoice = sync_invoice(data)

        if (
            event_type == "invoice.paid"
            and data.get("payment_intent")
        ):

            payment_intent_id = str(
                data["payment_intent"]
            )

            payment, _ = (
                Payment.objects.get_or_create(
                    provider=Provider.STRIPE,
                    provider_payment_id=(
                        payment_intent_id
                    ),
                    defaults={
                        "tenant": invoice.tenant,
                        "subscription": (
                            invoice.subscription
                        ),
                        "invoice": invoice,
                        "amount": int(
                            data.get("amount_paid")
                            or 0
                        ),
                        "currency": (
                            data.get("currency")
                            or "usd"
                        ).upper(),
                        "status": (
                            Payment.Status.SUCCEEDED
                        ),
                        "paid_at": timezone.now(),
                    },
                )
            )

            payment.tenant = invoice.tenant
            payment.subscription = (
                invoice.subscription
            )
            payment.invoice = invoice

            payment.amount = int(
                data.get("amount_paid")
                or payment.amount
                or 0
            )

            payment.currency = (
                data.get("currency")
                or payment.currency
            ).upper()

            payment.status = (
                Payment.Status.SUCCEEDED
            )

            payment.paid_at = (
                payment.paid_at
                or timezone.now()
            )

            payment.save()

        return

    # ========================================================
    # Payment intent
    # ========================================================

    if event_type in {
        "payment_intent.succeeded",
        "payment_intent.payment_failed",
    }:

        payment_intent_id = str(
            data.get("id") or ""
        )

        customer_id = str(
            data.get("customer") or ""
        )

        product_id = str(
            data.get("product_id") or ""
        )

        if not payment_intent_id:
            return

        if not customer_id:
            return

        from ..models import BillingCustomer

        customer = (
            BillingCustomer.objects
            .select_related("tenant")
            .filter(
                provider=Provider.STRIPE,
                provider_customer_id=customer_id,
            )
            .first()
        )

        if not customer:
            logger.warning(
                "PaymentIntent %s references "
                "unknown customer %s",
                payment_intent_id,
                customer_id,
            )
            return

        succeeded = (
            event_type
            == "payment_intent.succeeded"
        )

        payment, created = (
            Payment.objects.get_or_create(
                provider=Provider.STRIPE,
                provider_payment_id=payment_intent_id,
                defaults={
                    "tenant": customer.tenant,
                    "amount": int(
                        data.get("amount_received")
                        or data.get("amount")
                        or 0
                    ),
                    "currency": (
                        data.get("currency")
                        or "usd"
                    ).upper(),
                    "status": (
                        Payment.Status.SUCCEEDED
                        if succeeded
                        else Payment.Status.FAILED
                    ),
                    "paid_at": (
                        timezone.now()
                        if succeeded
                        else None
                    ),
                },
            )
        )

        payment.status = (
            Payment.Status.SUCCEEDED
            if succeeded
            else Payment.Status.FAILED
        )

        payment.save()

        if succeeded:
            if customer_id and product_id:
                
                product = Product.objects.get(id=product_id)

                send_mail(
                    subject="Here is your invoice",
                    message=f"Thanks for your purchase.Your subscription for {product.name} has been activated successfully.",
                    recipient_list=[customer.email],
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "admin@test.com")
                )

        return

    # ========================================================
    # Unknown / ignored event
    # ========================================================

    logger.debug(
        "Ignoring Stripe event: "
        "id=%s type=%s",
        event_id,
        event_type,
    )