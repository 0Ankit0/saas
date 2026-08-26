# billing/services/webhook.py

import logging
from typing import Any

from django.utils import timezone

from saas.billing.services.payment import (
    finalize_one_time_payment,
)

from ..models import (
    CheckoutSession,
    Payment,
    Provider,
    Subscription,
)
from .stripe import (
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

    # ========================================================
    # Stripe Checkout Session Completed
    # ========================================================

    if event_type == "checkout.session.completed":

        stripe_session_id = str(
            data.get("id") or ""
        )

        if not stripe_session_id:
            logger.warning(
                "Stripe checkout.session.completed "
                "has no session ID."
            )
            return

        session = (
            CheckoutSession.objects
            .filter(
                provider=Provider.STRIPE,
                provider_session_id=(
                    stripe_session_id
                ),
            )
            .first()
        )

        if not session:
            logger.warning(
                "Stripe CheckoutSession %s does not "
                "exist in our database.",
                stripe_session_id,
            )
            return

        payment_status = str(
            data.get("payment_status") or ""
        ).lower()

        # Keep a copy of the Stripe Checkout state.
        session.status = (
            data.get("status")
            or "complete"
        )

        session.completed_at = (
            session.completed_at
            or timezone.now()
        )

        session.metadata = {
            **(
                session.metadata
                or {}
            ),
            "stripe_checkout": data,
        }

        session.save(
            update_fields=[
                "status",
                "completed_at",
                "metadata",
                "updated_at",
            ]
        )

        # ----------------------------------------------------
        # Recurring Stripe Checkout
        # ----------------------------------------------------
        #
        # IMPORTANT:
        #
        # checkout.session.completed means the Checkout
        # Session completed. It should NOT be treated as
        # proof that the subscription's invoice was paid.
        #
        # Subscription/invoice events are authoritative for
        # the recurring billing state.
        # ----------------------------------------------------

        if session.price.is_recurring:
            return

        # ----------------------------------------------------
        # ONE-TIME Stripe Checkout
        # ----------------------------------------------------

        if payment_status != "paid":

            logger.info(
                "Stripe CheckoutSession %s completed "
                "without a paid payment: payment_status=%s.",
                stripe_session_id,
                payment_status,
            )

            # Do NOT finalize the local payment here.
            #
            # For asynchronous payment methods Stripe will
            # later send:
            #
            # checkout.session.async_payment_succeeded
            #
            return

        _finalize_checkout_payment(
            session=session,
            data=data,
        )

        return

    # ========================================================
    # Stripe Checkout async payment succeeded
    # ========================================================

    if event_type == "checkout.session.async_payment_succeeded":

        stripe_session_id = str(
            data.get("id") or ""
        )

        if not stripe_session_id:
            logger.warning(
                "Stripe async payment succeeded event "
                "has no session ID."
            )
            return

        session = (
            CheckoutSession.objects
            .filter(
                provider=Provider.STRIPE,
                provider_session_id=(
                    stripe_session_id
                ),
            )
            .first()
        )

        if not session:
            logger.warning(
                "Stripe async CheckoutSession %s "
                "does not exist.",
                stripe_session_id,
            )
            return

        if session.price.is_recurring:
            logger.info(
                "Ignoring async payment success for "
                "recurring CheckoutSession %s.",
                stripe_session_id,
            )
            return

        # This event itself means the async payment
        # succeeded, so finalize the one-time payment.
        _finalize_checkout_payment(
            session=session,
            data=data,
        )

        return

    # ========================================================
    # Stripe Checkout async payment failed
    # ========================================================

    if event_type == "checkout.session.async_payment_failed":

        stripe_session_id = str(
            data.get("id") or ""
        )

        if not stripe_session_id:
            logger.warning(
                "Stripe async payment failed event "
                "has no session ID."
            )
            return

        session = (
            CheckoutSession.objects
            .filter(
                provider=Provider.STRIPE,
                provider_session_id=(
                    stripe_session_id
                ),
            )
            .first()
        )

        if not session:
            logger.warning(
                "Stripe async CheckoutSession %s "
                "does not exist.",
                stripe_session_id,
            )
            return

        session.status = "failed"

        session.metadata = {
            **(
                session.metadata
                or {}
            ),
            "stripe_checkout": data,
        }

        session.save(
            update_fields=[
                "status",
                "metadata",
                "updated_at",
            ]
        )

        return

    # ========================================================
    # Stripe Subscription Created / Updated
    # ========================================================

    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
    }:

        sync_subscription(data)

        return

    # ========================================================
    # Stripe Subscription Deleted
    # ========================================================

    if event_type == "customer.subscription.deleted":

        subscription = (
            Subscription.objects
            .filter(
                provider=Provider.STRIPE,
                provider_subscription_id=(
                    data.get("id")
                ),
            )
            .first()
        )

        if not subscription:

            logger.warning(
                "Stripe subscription %s does not exist.",
                data.get("id"),
            )

            return

        subscription.status = (
            Subscription.Status.CANCELED
        )

        subscription.cancel_at_period_end = False

        subscription.canceled_at = (
            subscription.canceled_at
            or timezone.now()
        )

        subscription.save(
            update_fields=[
                "status",
                "cancel_at_period_end",
                "canceled_at",
                "updated_at",
            ]
        )

        return

    # ========================================================
    # Stripe Invoice Events
    # ========================================================

    if event_type.startswith("invoice."):

        invoice = sync_invoice(data)

        # ----------------------------------------------------
        # Invoice paid
        # ----------------------------------------------------

        if (
            event_type == "invoice.paid"
            and data.get("payment_intent")
        ):

            payment_intent_id = str(
                data["payment_intent"]
            )

            amount_paid = int(
                data.get("amount_paid") or 0
            )

            currency = str(
                data.get("currency")
                or "usd"
            ).upper()

            payment, created = (
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
                        "amount": amount_paid,
                        "currency": currency,
                        "status": (
                            Payment.Status.SUCCEEDED
                        ),
                        "paid_at": timezone.now(),
                    },
                )
            )

            # Make retries idempotent.
            payment.tenant = invoice.tenant
            payment.subscription = (
                invoice.subscription
            )
            payment.invoice = invoice

            if amount_paid:
                payment.amount = amount_paid

            payment.currency = currency

            payment.status = (
                Payment.Status.SUCCEEDED
            )

            payment.paid_at = (
                payment.paid_at
                or timezone.now()
            )

            payment.save()

        # ----------------------------------------------------
        # Invoice payment failed
        # ----------------------------------------------------

        elif event_type == "invoice.payment_failed":

            payment_intent_id = str(
                data.get("payment_intent")
                or ""
            )

            if payment_intent_id:

                payment = (
                    Payment.objects
                    .filter(
                        provider=Provider.STRIPE,
                        provider_payment_id=(
                            payment_intent_id
                        ),
                    )
                    .first()
                )

                if payment:

                    payment.status = (
                        Payment.Status.FAILED
                    )

                    payment.save(
                        update_fields=[
                            "status",
                            "updated_at",
                        ]
                    )

        return

    # ========================================================
    # Stripe PaymentIntent events
    # ========================================================
    #
    # These are deliberately NOT used to create local
    # Checkout payments.
    #
    # CheckoutSession events remain authoritative for
    # Checkout one-time payments.
    #
    # PaymentIntent events can still be useful for
    # reconciliation/debugging.
    # ========================================================

    if event_type in {
        "payment_intent.succeeded",
        "payment_intent.payment_failed",
    }:

        logger.debug(
            "Ignoring Stripe PaymentIntent event %s "
            "for local payment creation. "
            "Checkout Session / Invoice events are "
            "authoritative for the corresponding flow.",
            event_type,
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


# ============================================================
# Helpers
# ============================================================

def _finalize_checkout_payment(
    *,
    session: CheckoutSession,
    data: dict[str, Any],
) -> None:

    stripe_session_id = str(
        data.get("id") or ""
    )

    payment_status = str(
        data.get("payment_status") or ""
    ).lower()

    if payment_status and payment_status != "paid":

        logger.warning(
            "Refusing to finalize CheckoutSession %s "
            "because payment_status=%s.",
            stripe_session_id,
            payment_status,
        )

        return

    amount = int(
        data.get("amount_total") or 0
    )

    currency = str(
        data.get(
            "currency",
            session.price.currency,
        )
    ).upper()

    payment_intent = str(
        data.get("payment_intent") or ""
    )

    if not payment_intent:

        logger.error(
            "Stripe CheckoutSession %s has no "
            "payment_intent.",
            stripe_session_id,
        )

        return

    finalize_one_time_payment(
        session,
        provider_payment_id=payment_intent,
        amount=amount,
        currency=currency,
        provider_response=data,
    )