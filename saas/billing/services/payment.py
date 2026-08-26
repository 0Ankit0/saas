# billing/services/payment.py

import logging
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from ..models import (
    BillingCustomer,
    CheckoutSession,
    Invoice,
    Payment,
    Subscription,
)

logger = logging.getLogger(__name__)


def _get_billing_customer(
    checkout: CheckoutSession,
) -> BillingCustomer:
    """
    Return the existing billing customer for the tenant/provider.

    A tenant is expected to have exactly one BillingCustomer
    for each provider.

    We deliberately DO NOT create a customer here.

    The billing customer's stored name/email are the source of
    truth for payment-related communication.
    """

    customer = (
        BillingCustomer.objects
        .filter(
            tenant=checkout.tenant,
            provider=checkout.provider,
        )
        .first()
    )

    if not customer:
        raise ValueError(
            "No billing customer exists for this tenant "
            f"and provider '{checkout.provider}'."
        )

    return customer


def _send_payment_success_email(
    *,
    checkout: CheckoutSession,
    customer: BillingCustomer,
) -> None:
    """
    Send the purchase confirmation.

    Email failure must never roll back an already successful
    payment.
    """

    if not customer.email:
        logger.warning(
            "Billing customer %s has no email address.",
            customer.pk,
        )
        return

    try:
        product = checkout.price.product

        send_mail(
            subject="Your purchase was successful",
            message=(
                "Thanks for your purchase.\n\n"
                f"Your subscription for "
                f"{product.name} has been activated "
                "successfully.\n\n"
                f"Amount: {checkout.price.amount_display}"
            ),
            recipient_list=[
                customer.email,
            ],
            from_email=getattr(
                settings,
                "DEFAULT_FROM_EMAIL",
                "admin@test.com",
            ),
            fail_silently=False,
        )

    except Exception:
        logger.exception(
            "Could not send payment success email "
            "for checkout_session=%s",
            checkout.pk,
        )


def finalize_one_time_payment(
    checkout_session: CheckoutSession,
    *,
    provider_payment_id: str,
    amount: int,
    currency: str,
    provider_response: dict[str, Any] | None = None,
) -> Payment:
    """
    Atomically finalize a successful one-time payment.

    This is the ONLY function that should create the local:

        Payment
        Invoice
        Subscription

    for one-time purchases.

    Stripe, Khalti and eSewa should all eventually call this
    function after independently verifying that the external
    payment was actually successful.

    Idempotent:
        Repeated calls for the same provider payment will not
        create duplicate Payment/Invoice/Subscription rows.
    """

    if not provider_payment_id:
        raise ValueError(
            "Provider payment ID is required."
        )

    currency = str(
        currency or ""
    ).upper()

    with transaction.atomic():

        # ----------------------------------------------------
        # Lock checkout
        # ----------------------------------------------------

        checkout = (
            CheckoutSession.objects
            .select_for_update()
            .select_related(
                "price",
                "price__product",
                "tenant",
            )
            .get(
                pk=checkout_session.pk,
            )
        )

        # ----------------------------------------------------
        # Validate checkout type
        # ----------------------------------------------------

        if checkout.price.is_recurring:
            raise ValueError(
                "This checkout is recurring. "
                "One-time payment finalization cannot "
                "be used for a recurring price."
            )

        # ----------------------------------------------------
        # Idempotency
        # ----------------------------------------------------

        existing_payment = (
            Payment.objects
            .select_for_update()
            .filter(
                provider=checkout.provider,
                provider_payment_id=(
                    provider_payment_id
                ),
            )
            .first()
        )

        if existing_payment:

            # A successful payment has already been processed.
            #
            # Do not create another subscription, invoice,
            # payment, or email.
            if (
                existing_payment.status
                == Payment.Status.SUCCEEDED
            ):
                return existing_payment

            # If the same provider payment ID already exists
            # but belongs to another tenant/checkout, this is
            # an integrity problem and must never be silently
            # overwritten.
            if existing_payment.tenant_id != checkout.tenant_id:
                raise ValueError(
                    "Provider payment already belongs "
                    "to another tenant."
                )

        # ----------------------------------------------------
        # If checkout was already completed, try to return its
        # existing payment instead of creating another one.
        # ----------------------------------------------------

        if (
            checkout.status == "complete"
            and checkout.completed_at
        ):

            payment = (
                Payment.objects
                .filter(
                    tenant=checkout.tenant,
                    provider=checkout.provider,
                    metadata__checkout_session_id=checkout.pk,
                    status=Payment.Status.SUCCEEDED,
                )
                .first()
            )

            if payment:
                return payment

            raise RuntimeError(
                "CheckoutSession is marked complete but "
                "its successful payment does not exist."
            )

        # ----------------------------------------------------
        # Validate amount
        # ----------------------------------------------------

        expected_amount = int(
            checkout.price.amount
        )

        if int(amount) != expected_amount:
            raise ValueError(
                "Payment amount does not match "
                "the checkout price."
            )

        # ----------------------------------------------------
        # Validate currency
        # ----------------------------------------------------

        expected_currency = (
            checkout.price.currency.upper()
        )

        if currency != expected_currency:
            raise ValueError(
                "Payment currency does not match "
                "the checkout price."
            )

        # ----------------------------------------------------
        # Existing billing customer
        # ----------------------------------------------------

        customer = _get_billing_customer(
            checkout
        )

        now = timezone.now()

        # ----------------------------------------------------
        # Invoice
        # ----------------------------------------------------

        invoice_provider_id = (
            f"checkout:{checkout.pk}"
        )

        invoice = (
            Invoice.objects
            .select_for_update()
            .filter(
                provider=checkout.provider,
                provider_invoice_id=(
                    invoice_provider_id
                ),
            )
            .first()
        )

        if invoice is None:

            invoice = Invoice.objects.create(
                tenant=checkout.tenant,
                provider=checkout.provider,
                provider_invoice_id=(
                    invoice_provider_id
                ),
                number=(
                    f"INV-{checkout.pk}"
                ),
                status=Invoice.Status.PAID,
                amount_due=expected_amount,
                amount_paid=expected_amount,
                currency=expected_currency,
                paid_at=now,
                period_start=now,
                period_end=None,
                metadata={
                    "checkout_session_id": (
                        checkout.pk
                    ),
                    "provider_payment_id": (
                        provider_payment_id
                    ),
                    "one_time": True,
                },
            )

        # ----------------------------------------------------
        # Payment
        # ----------------------------------------------------

        if existing_payment is None:

            payment = Payment.objects.create(
                tenant=checkout.tenant,
                subscription=None,
                invoice=invoice,
                amount=expected_amount,
                currency=expected_currency,
                status=Payment.Status.SUCCEEDED,
                provider=checkout.provider,
                provider_payment_id=(
                    provider_payment_id
                ),
                paid_at=now,
                metadata={
                    "checkout_session_id": (
                        checkout.pk
                    ),
                    "provider_response": (
                        provider_response
                        or {}
                    ),
                },
            )

        else:

            payment = existing_payment

            payment.tenant = checkout.tenant
            payment.invoice = invoice
            payment.amount = expected_amount
            payment.currency = expected_currency
            payment.status = Payment.Status.SUCCEEDED
            payment.paid_at = (
                payment.paid_at
                or now
            )

            payment.metadata = {
                **(
                    payment.metadata
                    or {}
                ),
                "checkout_session_id": (
                    checkout.pk
                ),
                "provider_response": (
                    provider_response
                    or {}
                ),
            }

            payment.save()

        # ----------------------------------------------------
        # Subscription
        # ----------------------------------------------------

        subscription = (
            Subscription.objects
            .select_for_update()
            .filter(
                tenant=checkout.tenant,
                price=checkout.price,
                status=Subscription.Status.ACTIVE,
            )
            .first()
        )

        if subscription is None:

            subscription_provider_id = (
                f"{checkout.provider}:"
                f"{provider_payment_id}"
            )

            subscription = (
                Subscription.objects.create(
                    tenant=checkout.tenant,
                    price=checkout.price,
                    status=(
                        Subscription.Status.ACTIVE
                    ),
                    provider=checkout.provider,
                    provider_subscription_id=(
                        subscription_provider_id
                    ),
                    customer=customer,
                    current_period_start=now,

                    # ONE_TIME currently means lifetime
                    # access because your Price model has
                    # no expiration duration.
                    current_period_end=None,

                    cancel_at_period_end=False,

                    metadata={
                        "one_time": True,
                        "checkout_session_id": (
                            checkout.pk
                        ),
                        "provider_payment_id": (
                            provider_payment_id
                        ),
                        "provider_response": (
                            provider_response
                            or {}
                        ),
                    },
                )
            )

        else:

            # The same checkout may have reached this function
            # again after a race/retry.
            #
            # If the existing subscription already belongs to
            # this checkout/payment, it is safe to reuse it.
            existing_checkout_id = (
                subscription.metadata or {}
            ).get(
                "checkout_session_id"
            )

            if (
                existing_checkout_id
                not in {None, checkout.pk}
            ):
                raise ValueError(
                    "Tenant already has an active "
                    "subscription for this price."
                )

        # ----------------------------------------------------
        # Link Payment -> Subscription
        # ----------------------------------------------------

        payment.subscription = subscription
        payment.invoice = invoice

        payment.save(
            update_fields=[
                "subscription",
                "invoice",
                "updated_at",
            ]
        )

        # ----------------------------------------------------
        # Link Invoice -> Subscription
        # ----------------------------------------------------

        invoice.subscription = subscription

        invoice.save(
            update_fields=[
                "subscription",
                "updated_at",
            ]
        )

        # ----------------------------------------------------
        # CheckoutSession
        # ----------------------------------------------------

        checkout.status = "complete"

        checkout.completed_at = (
            checkout.completed_at
            or now
        )

        checkout.metadata = {
            **(
                checkout.metadata
                or {}
            ),
            "provider_payment_id": (
                provider_payment_id
            ),
            "payment_id": payment.pk,
            "subscription_id": (
                subscription.pk
            ),
            "invoice_id": invoice.pk,
        }

        checkout.save(
            update_fields=[
                "status",
                "completed_at",
                "metadata",
            ]
        )

    # --------------------------------------------------------
    # Email only after successful database commit.
    # --------------------------------------------------------

    _send_payment_success_email(
        checkout=checkout,
        customer=customer,
    )

    return payment


def mark_checkout_failed(
    checkout_session: CheckoutSession,
    *,
    reason: str = "",
) -> None:
    """
    Mark an unfinished checkout as failed/cancelled.

    No Payment/Invoice/Subscription is created.
    """

    with transaction.atomic():

        checkout = (
            CheckoutSession.objects
            .select_for_update()
            .get(
                pk=checkout_session.pk
            )
        )

        # Never change a successful checkout.
        if checkout.status == "complete":
            return

        checkout.status = "failed"

        checkout.metadata = {
            **(
                checkout.metadata
                or {}
            ),
            "failure_reason": reason,
        }

        checkout.save(
            update_fields=[
                "status",
                "metadata",
            ]
        )