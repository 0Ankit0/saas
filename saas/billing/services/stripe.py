# billing/services/stripe.py

from datetime import datetime, timezone as dt_timezone
from typing import Any, cast

from django.urls import reverse
import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import (
    BillingCustomer,
    CheckoutSession,
    Currency,
    Invoice,
    Payment,
    Price,
    Product,
    Provider,
    Subscription,
)


def stripe_client() -> stripe.StripeClient:
    if not settings.ENABLE_STRIPE:
        raise RuntimeError(
            "Stripe integration is disabled."
        )

    if not settings.STRIPE_API_KEY:
        raise RuntimeError(
            "STRIPE_API_KEY is not configured."
        )

    return stripe.StripeClient(
        settings.STRIPE_API_KEY
    )


def stripe_dict(resource: Any) -> dict[str, Any]:
    if isinstance(resource, dict):
        return resource

    if hasattr(resource, "to_dict_recursive"):
        return resource.to_dict_recursive()

    if hasattr(resource, "to_dict"):
        return resource.to_dict()

    raise TypeError(
        f"Unsupported Stripe resource: "
        f"{type(resource).__name__}"
    )


def stripe_datetime(
    value: Any,
) -> datetime | None:

    if value in (None, ""):
        return None

    return datetime.fromtimestamp(
        int(value),
        tz=dt_timezone.utc,
    )


# ============================================================
# Product
# ============================================================

def create_stripe_product(
    product: Product,
) -> Product:

    if product.provider_product_id:
        return product

    response = stripe_client().v1.products.create(
        cast(
            Any,
            {
                "name": product.name,
                "description": product.description,
                "active": product.active,
                "metadata": {
                    "product_id": str(product.pk),
                    **{
                        str(k): str(v)
                        for k, v in product.metadata.items()
                    },
                },
            },
        )
    )

    data = stripe_dict(response)

    product.provider_product_id = data["id"]
    product.save(
        update_fields=[
            "provider_product_id",
            "updated_at",
        ]
    )

    return product


# ============================================================
# Price
# ============================================================

def create_stripe_price(
    price: Price,
) -> Price:

    if price.provider_price_id:
        return price

    if not price.product.provider_product_id:
        raise ValueError(
            "Product must have a Stripe product ID "
            "before creating a Stripe price."
        )

    params: dict[str, Any] = {
        "product": price.product.provider_product_id,
        "unit_amount": price.amount,
        "currency": price.currency.lower(),
        "active": price.active,
    }

    if price.is_recurring:
        params["recurring"] = {
            "interval": price.interval,
            "interval_count": price.interval_count,
        }

    if price.metadata:
        params["metadata"] = {
            str(k): str(v)
            for k, v in price.metadata.items()
        }

    response = stripe_client().v1.prices.create(
        cast(Any, params)
    )

    data = stripe_dict(response)

    price.provider_price_id = data["id"]

    price.save(
        update_fields=[
            "provider_price_id",
            "updated_at",
        ]
    )

    return price


# ============================================================
# Customer
# ============================================================

def create_stripe_customer(
    customer: BillingCustomer,
) -> BillingCustomer:

    if customer.provider_customer_id:
        return customer

    response = stripe_client().v1.customers.create(
        cast(
            Any,
            {
                "email": customer.email,
                "name": customer.name,
                "metadata": {
                    "tenant_id": str(
                        customer.tenant_id
                    ),
                },
            },
        )
    )

    data = stripe_dict(response)

    customer.provider_customer_id = data["id"]

    customer.save(
        update_fields=[
            "provider_customer_id",
            "updated_at",
        ]
    )

    return customer


# ============================================================
# Checkout
# ============================================================

def create_checkout_session(
    *,
    tenant,
    price: Price,
    success_url: str,
    cancel_url: str,
) -> CheckoutSession:

    if not price.provider_price_id:
        raise ValueError(
            "Price does not have a Stripe price ID."
        )

    customer = BillingCustomer.objects.filter(
        tenant=tenant,
        provider=Provider.STRIPE,
    ).first()

    if not customer:
        raise ValueError(
            "Billing customer does not exist."
        )

    if not customer.provider_customer_id:
        raise ValueError(
            "Billing customer does not have "
            "a Stripe customer ID."
        )

    mode = (
        CheckoutSession.Mode.SUBSCRIPTION
        if price.is_recurring
        else CheckoutSession.Mode.PAYMENT
    )

    params = {
        "customer": customer.provider_customer_id,
        "line_items": [
            {
                "price": price.provider_price_id,
                "quantity": 1,
            }
        ],
        "mode": mode,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {
            "tenant_id": str(tenant.pk),
            "price_id": str(price.pk),
        },
    }

    response = (
        stripe_client()
        .v1
        .checkout
        .sessions
        .create(
            cast(Any, params)
        )
    )

    data = stripe_dict(response)

    return CheckoutSession.objects.create(
        tenant=tenant,
        price=price,
        provider=Provider.STRIPE,
        provider_session_id=data["id"],
        mode=mode,
        status=data.get("status") or "open",
        url=data.get("url") or "",
        metadata=data.get("metadata") or {},
    )


# ============================================================
# Subscription synchronization
# ============================================================

@transaction.atomic
def sync_subscription(
    data: dict[str, Any],
) -> Subscription:

    subscription_id = str(
        data.get("id") or ""
    )

    customer_id = str(
        data.get("customer") or ""
    )

    if not subscription_id:
        raise ValueError(
            "Stripe subscription has no ID."
        )

    if not customer_id:
        raise ValueError(
            f"Stripe subscription "
            f"{subscription_id} has no customer."
        )

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
        raise ValueError(
            f"No local BillingCustomer exists for "
            f"Stripe customer {customer_id}."
        )

    items = (
        data.get("items") or {}
    ).get("data") or []

    if not items:
        raise ValueError(
            f"Stripe subscription "
            f"{subscription_id} has no items."
        )

    stripe_price = (
        items[0].get("price") or {}
    )

    if isinstance(
        stripe_price,
        dict,
    ):
        stripe_price_id = str(
            stripe_price.get("id") or ""
        )
    else:
        stripe_price_id = str(
            stripe_price or ""
        )

    if not stripe_price_id:
        raise ValueError(
            f"Stripe subscription "
            f"{subscription_id} has no price."
        )

    price = (
        Price.objects
        .select_related("product")
        .filter(
            provider_price_id=stripe_price_id,
        )
        .first()
    )

    if not price:
        raise ValueError(
            f"No local Price exists for Stripe price "
            f"{stripe_price_id}."
        )

    status = (
        data.get("status")
        or Subscription.Status.INCOMPLETE
    )

    subscription, _ = (
        Subscription.objects.select_for_update()
        .get_or_create(
            provider=Provider.STRIPE,
            provider_subscription_id=subscription_id,
            defaults={
                "tenant": customer.tenant,
                "customer": customer,
                "price": price,
                "status": status,
            },
        )
    )

    subscription.tenant = customer.tenant
    subscription.customer = customer
    subscription.price = price
    subscription.status = status

    subscription.current_period_start = (
        stripe_datetime(
            data.get("current_period_start")
        )
    )

    subscription.current_period_end = (
        stripe_datetime(
            data.get("current_period_end")
        )
    )

    subscription.cancel_at_period_end = bool(
        data.get(
            "cancel_at_period_end",
            False,
        )
    )

    subscription.canceled_at = stripe_datetime(
        data.get("canceled_at")
    )

    subscription.trial_end = stripe_datetime(
        data.get("trial_end")
    )

    subscription.metadata = (
        data.get("metadata") or {}
    )

    subscription.save()

    return subscription


# ============================================================
# Invoice synchronization
# ============================================================

@transaction.atomic
def sync_invoice(
    data: dict[str, Any],
) -> Invoice:

    invoice_id = str(
        data.get("id") or ""
    )

    customer_id = str(
        data.get("customer") or ""
    )

    if not invoice_id:
        raise ValueError(
            "Stripe invoice has no ID."
        )

    if not customer_id:
        raise ValueError(
            f"Stripe invoice {invoice_id} "
            "has no customer."
        )

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
        raise ValueError(
            f"No local BillingCustomer exists for "
            f"Stripe customer {customer_id}."
        )

    subscription_id = str(
        data.get("subscription") or ""
    )

    subscription = None

    if subscription_id:
        subscription = (
            Subscription.objects
            .filter(
                provider=Provider.STRIPE,
                provider_subscription_id=subscription_id,
            )
            .first()
        )

    invoice, _ = Invoice.objects.get_or_create(
        provider=Provider.STRIPE,
        provider_invoice_id=invoice_id,
        defaults={
            "tenant": customer.tenant,
            "subscription": subscription,
            "status": (
                data.get("status")
                or Invoice.Status.DRAFT
            ),
        },
    )

    invoice.tenant = customer.tenant
    invoice.subscription = subscription

    invoice.number = data.get("number") or ""

    invoice.status = (
        data.get("status")
        or Invoice.Status.DRAFT
    )

    invoice.amount_due = int(
        data.get("amount_due") or 0
    )

    invoice.amount_paid = int(
        data.get("amount_paid") or 0
    )

    invoice.currency = (
        data.get("currency")
        or Currency.USD
    ).upper()

    invoice.hosted_invoice_url = (
        data.get("hosted_invoice_url")
        or ""
    )

    invoice.invoice_pdf = (
        data.get("invoice_pdf")
        or ""
    )

    invoice.period_start = stripe_datetime(
        data.get("period_start")
    )

    invoice.period_end = stripe_datetime(
        data.get("period_end")
    )

    if invoice.status == Invoice.Status.PAID:
        invoice.paid_at = (
            invoice.paid_at
            or timezone.now()
        )

    invoice.metadata = (
        data.get("metadata") or {}
    )

    invoice.save()

    return invoice

# ============================================================
# Current subscription
# ============================================================

def get_current_subscription(
    tenant,
) -> Subscription | None:
    """
    Return the tenant's current active Stripe subscription.

    This is a local database lookup. Stripe webhooks are
    responsible for keeping the local subscription record
    synchronized with Stripe.
    """

    return (
        Subscription.objects
        .select_related(
            "customer",
            "price",
            "price__product",
        )
        .filter(
            tenant=tenant,
            provider=Provider.STRIPE,
            status__in=[
                Subscription.Status.ACTIVE,
                Subscription.Status.TRIALING,
            ],
        )
        .order_by("-created_at")
        .first()
    )


# ============================================================
# Stripe Billing Portal
# ============================================================

def create_portal_session(
    request,
) -> str:
    """
    Create a Stripe Billing Portal session for the current
    tenant and return its URL.
    """

    tenant = request.tenant

    customer = (
        BillingCustomer.objects
        .filter(
            tenant=tenant,
            provider=Provider.STRIPE,
        )
        .first()
    )

    if not customer:
        raise ValueError(
            "Stripe billing customer does not exist."
        )

    if not customer.provider_customer_id:
        raise ValueError(
            "Stripe billing customer does not have "
            "a Stripe customer ID."
        )

    return_url = request.build_absolute_uri(
        reverse("billing:dashboard")
    )

    response = (
        stripe_client()
        .v1
        .billing_portal
        .sessions
        .create(
            cast(
                Any,
                {
                    "customer": customer.provider_customer_id,
                    "return_url": return_url,
                },
            )
        )
    )

    data = stripe_dict(response)

    url = data.get("url")

    if not url:
        raise RuntimeError(
            "Stripe did not return a billing portal URL."
        )

    return str(url)


# ============================================================
# Cancel Stripe subscription
# ============================================================

def cancel_subscription(
    subscription: Subscription,
    *,
    at_period_end: bool = True,
) -> Subscription:
    """
    Cancel a Stripe subscription.

    By default the subscription remains active until the end
    of the current billing period.

    The local subscription is not immediately marked canceled
    when at_period_end=True. Stripe's webhook will synchronize
    the final state.
    """

    if subscription.provider != Provider.STRIPE:
        raise ValueError(
            "Only Stripe subscriptions can be canceled "
            "through the Stripe service."
        )

    stripe_subscription_id = (
        subscription.provider_subscription_id
    )

    if not stripe_subscription_id:
        raise ValueError(
            "Subscription does not have a Stripe "
            "subscription ID."
        )

    client = stripe_client()

    if at_period_end:

        response = (
            client
            .v1
            .subscriptions
            .update(
                stripe_subscription_id,
                cast(
                    Any,
                    {
                        "cancel_at_period_end": True,
                    },
                ),
            )
        )

    else:

        response = (
            client
            .v1
            .subscriptions
            .cancel(
                stripe_subscription_id,
            )
        )

    data = stripe_dict(response)

    # Keep the local record synchronized immediately.
    # The Stripe webhook remains the authoritative source.
    subscription.cancel_at_period_end = bool(
        data.get(
            "cancel_at_period_end",
            at_period_end,
        )
    )

    subscription.canceled_at = stripe_datetime(
        data.get("canceled_at")
    )

    if not at_period_end:
        subscription.status = (
            data.get("status")
            or Subscription.Status.CANCELED
        )

    subscription.metadata = (
        data.get("metadata")
        or subscription.metadata
        or {}
    )

    subscription.save(
        update_fields=[
            "cancel_at_period_end",
            "canceled_at",
            "status",
            "metadata",
            "updated_at",
        ]
    )

    return subscription