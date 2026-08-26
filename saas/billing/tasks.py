# billing/tasks.py

import logging
import traceback

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import (
    BillingCustomer,
    Price,
    Product,
    Provider,
    WebhookEvent,
)
from .services.stripe import (
    create_stripe_customer,
    create_stripe_price,
    create_stripe_product,
)
from .services.stripe_webhooks import process_webhook

logger = logging.getLogger(__name__)


# ============================================================
# Stripe Product
# ============================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
)
def create_stripe_product_task(
    self,
    product_id: int,
):

    product = Product.objects.get(
        pk=product_id
    )

    if product.provider_product_id:
        return product.provider_product_id

    product = create_stripe_product(
        product
    )

    logger.info(
        "Stripe product created: "
        "local_id=%s stripe_id=%s",
        product.pk,
        product.provider_product_id,
    )

    return product.provider_product_id


# ============================================================
# Stripe Price
# ============================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
)
def create_stripe_price_task(
    self,
    price_id: int,
):

    price = (
        Price.objects
        .select_related("product")
        .get(pk=price_id)
    )

    if price.provider_price_id:
        return price.provider_price_id

    if not price.product.provider_product_id:
        create_stripe_product_task.delay(
            price.product_id
        )

        raise RuntimeError(
            "Stripe product is not ready yet. "
            "Price task will be retried."
        )

    price = create_stripe_price(
        price
    )

    logger.info(
        "Stripe price created: "
        "local_id=%s stripe_id=%s",
        price.pk,
        price.provider_price_id,
    )

    return price.provider_price_id


# ============================================================
# Stripe Customer
# ============================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
)
def create_stripe_customer_task(
    self,
    customer_id: int,
):

    customer = BillingCustomer.objects.get(
        pk=customer_id
    )

    if customer.provider != Provider.STRIPE:
        return None

    if customer.provider_customer_id:
        return customer.provider_customer_id

    customer = create_stripe_customer(
        customer
    )

    logger.info(
        "Stripe customer created: "
        "local_id=%s stripe_id=%s",
        customer.pk,
        customer.provider_customer_id,
    )

    return customer.provider_customer_id


# ============================================================
# Webhook
# ============================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
)
def process_stripe_webhook_task(
    self,
    webhook_id: int,
) -> None:

    try:

        with transaction.atomic():

            webhook = (
                WebhookEvent.objects
                .select_for_update()
                .get(pk=webhook_id)
            )

            if webhook.processed:
                logger.info(
                    "Stripe webhook already processed. "
                    "webhook_id=%s event_id=%s",
                    webhook.id,
                    webhook.event_id,
                )
                return

            logger.info(
                "Processing Stripe webhook. "
                "webhook_id=%s event_id=%s event_type=%s",
                webhook.id,
                webhook.event_id,
                webhook.event_type,
            )

            process_webhook(
                webhook.payload
            )

            webhook.processed = True
            webhook.processed_at = timezone.now()
            webhook.error = ""

            webhook.save(
                update_fields=[
                    "processed",
                    "processed_at",
                    "error",
                ]
            )

        logger.info(
            "Stripe webhook processed successfully. "
            "webhook_id=%s event_id=%s event_type=%s",
            webhook_id,
            webhook.event_id,
            webhook.event_type,
        )

    except WebhookEvent.DoesNotExist:

        logger.error(
            "Stripe webhook not found. webhook_id=%s",
            webhook_id,
        )

        return

    except Exception as exc:

        logger.exception(
            "Stripe webhook processing failed. "
            "webhook_id=%s",
            webhook_id,
        )

        # Save error OUTSIDE the failed transaction.
        WebhookEvent.objects.filter(
            pk=webhook_id
        ).update(
            processed=False,
            processed_at=None,
            error=(
                f"{type(exc).__name__}: {exc}"
            ),
        )

        raise
