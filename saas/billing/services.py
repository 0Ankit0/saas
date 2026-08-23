from typing import Literal
from stripe.billing_portal import Session
from stripe.checkout import Session as CheckoutSession

import stripe
from django.conf import settings

if settings.ENABLE_STRIPE:
    stripe.api_key = settings.STRIPE_API_KEY
else:
    raise Exception("Stripe is not enabled. Please set ENABLE_STRIPE to True in your settings.")

def create_provider_customer(
        name="",
        email="",
        metadata={},
        raw=False
    ):
    customer = stripe.Customer.create(
        name=name,
        email=email,
        metadata=metadata
    )
    if raw:
        return customer
    return customer.id

def create_provider_product(
        name="",
        description="",
        metadata={},
        raw=False
    ):
    product = stripe.Product.create(
        name=name,
        description=description,
        metadata=metadata
    )
    if raw:
        return product
    return product.id


StripeInterval = Literal["day", "week", "month", "year"]

STRIPE_INTERVAL_MAP: dict[str, StripeInterval] = {
    "day": "day",
    "week": "week",
    "month": "month",
    "year": "year",
}
def create_provider_price(
        product_id,
        unit_amount,
        currency,
        interval="month",
        interval_count=1,
        metadata={},
        raw=False
    ):
    if interval not in STRIPE_INTERVAL_MAP:
        raise ValueError(f"Invalid interval: {interval}. Must be one of {list(STRIPE_INTERVAL_MAP.keys())}")
    interval = STRIPE_INTERVAL_MAP[interval]
    price = stripe.Price.create(
        product=product_id,
        unit_amount=unit_amount,
        currency=currency,
        recurring={"interval": interval, "interval_count": interval_count},
        metadata=metadata
    )
    if raw:
        return price
    return price.id

def create_provider_subscription(
        customer_id,
        price_id,
        metadata={},
        raw=False
    ):
    subscription = stripe.Subscription.create(
        customer=customer_id,
        items=[{"price": price_id}],
        metadata=metadata
    )
    if raw:
        return subscription
    return subscription.id

def cancel_provider_subscription(
        subscription_id,
        cancel_at_period_end=True,
        metadata={},
        raw=False
    ):
    if cancel_at_period_end:
        subscription = stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True,
            metadata=metadata
        )
    subscription = stripe.Subscription.delete(
        subscription_id,
        metadata=metadata
    )

    if raw:
        return subscription
    return subscription.id

def create_provider_invoice(
        customer_id,
        metadata={},
        raw=False
    ):
    invoice = stripe.Invoice.create(
        customer=customer_id,
        metadata=metadata
    )
    if raw:
        return invoice
    return invoice.id

def create_provider_payment_intent(
        amount,
        currency,
        provider_customer_id="",
        metadata={},
        raw=False
    ):
    payment_intent = stripe.PaymentIntent.create(
        amount=amount,
        currency=currency,
        customer=provider_customer_id,
        metadata=metadata
    )
    if raw:
        return payment_intent
    return payment_intent.id

def create_provider_checkout_session(
        customer_id,
        price_id,
        success_url,
        cancel_url,
        metadata={},
        # raw=False
    )-> CheckoutSession:
    session = stripe.checkout.Session.create(
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata
    )
    return session
    # if raw:
    #     return session
    # return session.id