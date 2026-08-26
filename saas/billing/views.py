import json
import logging
from decimal import Decimal

from django.views import View
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from saas.billing.services.payment import mark_checkout_failed
from saas.billing.services.providers import validate_esewa_transaction

from .models import (
    CheckoutSession,
    Payment,
    Price,
    Product,
    Provider,
    WebhookEvent,
)
from .providers import (
    create_esewa_checkout,
    create_khalti_checkout,
    esewa_status,
    khalti_lookup,
    verify_esewa_response,
)
from .services.stripe import (
    cancel_subscription,
    create_checkout_session,
    create_portal_session,
    get_current_subscription,
    stripe_dict,
)
from .tasks import process_stripe_webhook_task


logger = logging.getLogger(__name__)


# ============================================================
# Provider helpers
# ============================================================

def provider_enabled(provider: Provider) -> bool:
    return bool(
        getattr(
            settings,
            f"ENABLE_{provider.value.upper()}",
            False,
        )
    )


def enabled_providers(
    price: Price,
) -> list[tuple[str, str]]:
    providers: list[tuple[str, str]] = []

    if provider_enabled(Provider.STRIPE):
        providers.append(
            (Provider.STRIPE, "Stripe")
        )

    if (
        provider_enabled(Provider.KHALTI)
        and price.currency.upper() == "NPR"
        and not price.is_recurring
    ):
        providers.append(
            (Provider.KHALTI, "Khalti")
        )

    if (
        provider_enabled(Provider.ESEWA)
        and price.currency.upper() == "NPR"
        and not price.is_recurring
    ):
        providers.append(
            (Provider.ESEWA, "eSewa")
        )

    return providers


# ============================================================
# Pricing
# ============================================================

@login_required
def pricing(
    request: HttpRequest,
) -> HttpResponse:

    prices = (
        Price.objects
        .select_related("product")
        .prefetch_related(
            "product__product_features__feature"
        )
        .filter(
            active=True,
            product__active=True,
        )
        .order_by(
            "product__name",
            "amount",
        )
    )

    subscription = get_current_subscription(
        request.tenant
    )

    cards = [
        (
            price,
            enabled_providers(price),
        )
        for price in prices
    ]

    return render(
        request,
        "billing/pricing.html",
        {
            "cards": cards,
            "subscription": subscription,
        },
    )


# ============================================================
# Billing dashboard
# ============================================================

@login_required
def dashboard(
    request: HttpRequest,
) -> HttpResponse:

    subscription = get_current_subscription(
        request.tenant
    )

    payments = (
        request.tenant.payments
        .select_related(
            "subscription__price__product",
            "invoice",
        )[:10]
    )

    invoices = (
        request.tenant.billing_invoices
        .select_related(
            "subscription__price__product",
        )[:10]
    )

    return render(
        request,
        "billing/dashboard.html",
        {
            "subscription": subscription,
            "payments": payments,
            "invoices": invoices,
        },
    )


# ============================================================
# Checkout
# ============================================================

@login_required
@require_POST
def checkout(
    request: HttpRequest,
    price_id: int,
) -> HttpResponse:

    price = get_object_or_404(
        Price,
        pk=price_id,
        active=True,
        product__active=True,
    )

    provider = request.POST.get(
        "provider",
        Provider.STRIPE,
    )

    available_providers = dict(
        enabled_providers(price)
    )

    if provider not in available_providers:
        messages.error(
            request,
            "That payment provider is not available "
            "for this price.",
        )

        return redirect(
            "billing:pricing"
        )

    # --------------------------------------------------------
    # Prevent duplicate active subscriptions
    # --------------------------------------------------------

    if price.is_recurring:
        current_subscription = (
            get_current_subscription(
                request.tenant
            )
        )

        if current_subscription:
            messages.info(
                request,
                "Your tenant already has an active "
                "subscription. Use the billing portal "
                "to manage it.",
            )

            return redirect(
                "billing:dashboard"
            )

    try:

        # ====================================================
        # Stripe
        # ====================================================

        if provider == Provider.STRIPE:

            checkout_session = create_checkout_session(
                tenant=request.tenant,
                price=price,
                success_url=request.build_absolute_uri(
                    reverse("billing:success")
                ),
                cancel_url=request.build_absolute_uri(
                    reverse("billing:pricing")
                ),
            )

            if not checkout_session.url:
                raise RuntimeError(
                    "Stripe did not return a checkout URL."
                )

            return redirect(
                checkout_session.url
            )

        # ====================================================
        # Khalti
        # ====================================================

        if provider == Provider.KHALTI:

            result = create_khalti_checkout(
                request,
                price,
            )

            CheckoutSession.objects.create(
                tenant=request.tenant,
                price=price,
                provider=provider,
                provider_session_id=result.reference,
                mode=CheckoutSession.Mode.PAYMENT,
                url=result.redirect_url,
                metadata={
                    "provider": provider,
                    **(
                        result.metadata
                        or {}
                    ),
                },
            )

            return redirect(
                result.redirect_url
            )

        # ====================================================
        # eSewa
        # ====================================================

        if provider == Provider.ESEWA:

            result = create_esewa_checkout(
                request,
                price,
            )

            CheckoutSession.objects.create(
                tenant=request.tenant,
                price=price,
                provider=provider,
                provider_session_id=result.reference,
                mode=CheckoutSession.Mode.PAYMENT,
                metadata={
                    "provider": provider,
                    **(
                        result.metadata
                        or {}
                    ),
                },
            )

            return render(
                request,
                "billing/esewa_redirect.html",
                {
                    "action": result.form_action,
                    "fields": result.form_fields,
                },
            )

        raise ValueError(
            f"Unsupported payment provider: {provider}"
        )

    except Exception as exc:

        logger.exception(
            "Failed to start checkout. "
            "tenant_id=%s price_id=%s provider=%s",
            getattr(
                request.tenant,
                "id",
                None,
            ),
            price.id,
            provider,
        )

        messages.error(
            request,
            f"Unable to start payment: {exc}",
        )

        return redirect(
            "billing:pricing"
        )


# ============================================================
# Stripe Billing Portal
# ============================================================

@login_required
@require_POST
def portal(
    request: HttpRequest,
) -> HttpResponse:

    try:

        portal_url = create_portal_session(
            request
        )

        return redirect(
            portal_url
        )

    except Exception as exc:

        logger.exception(
            "Failed to create Stripe billing portal "
            "session. tenant_id=%s",
            getattr(
                request.tenant,
                "id",
                None,
            ),
        )

        messages.error(
            request,
            f"Unable to open the Stripe billing portal: {exc}",
        )

        return redirect(
            "billing:dashboard"
        )


# ============================================================
# Cancel subscription
# ============================================================

@login_required
@require_POST
def cancel(
    request: HttpRequest,
) -> HttpResponse:

    subscription = get_current_subscription(
        request.tenant
    )

    if not subscription:

        messages.info(
            request,
            "There is no active subscription to cancel.",
        )

        return redirect(
            "billing:dashboard"
        )

    if subscription.provider != Provider.STRIPE:

        messages.info(
            request,
            "Local-wallet payments are one-time "
            "payments and do not have automatic cancellation.",
        )

        return redirect(
            "billing:dashboard"
        )

    try:

        cancel_subscription(
            subscription,
            at_period_end=True,
        )

        messages.success(
            request,
            "Your subscription will cancel at the "
            "end of the current billing period.",
        )

    except Exception as exc:

        logger.exception(
            "Failed to cancel Stripe subscription. "
            "tenant_id=%s subscription_id=%s "
            "stripe_subscription_id=%s",
            getattr(
                request.tenant,
                "id",
                None,
            ),
            subscription.id,
            subscription.provider_subscription_id,
        )

        messages.error(
            request,
            f"Unable to cancel the subscription: {exc}",
        )

    return redirect(
        "billing:dashboard"
    )


# ============================================================
# Checkout success
# ============================================================

@login_required
@require_GET
def success(
    request: HttpRequest,
) -> HttpResponse:

    return render(
        request,
        "billing/success.html",
        {
            "session_id": request.GET.get(
                "session_id",
                "",
            )
        },
    )


# ============================================================
# Khalti callback
# ============================================================

@require_GET
@csrf_exempt
def khalti_callback(
    request: HttpRequest,
) -> HttpResponse:

    pidx = str(
        request.GET.get(
            "pidx",
            "",
        )
    ).strip()

    if not pidx:
        messages.error(
            request,
            "Invalid Khalti payment response.",
        )

        return redirect(
            "billing:pricing"
        )

    try:

        checkout = get_object_or_404(
            CheckoutSession,
            provider=Provider.KHALTI,
            provider_session_id=pidx,
        )

        # ----------------------------------------------------
        # Always lookup with Khalti.
        # ----------------------------------------------------

        result = khalti_lookup(
            pidx
        )

        status = str(
            result.get(
                "status",
                "",
            )
        ).lower()

        # ----------------------------------------------------
        # Canceled / failed / pending
        # ----------------------------------------------------

        if status != "completed":

            mark_checkout_failed(
                checkout,
                reason=(
                    f"Khalti status: {status}"
                ),
            )

            if status == "pending":
                messages.info(
                    request,
                    "Your Khalti payment is "
                    "still pending.",
                )
            else:
                messages.error(
                    request,
                    "The Khalti payment was not "
                    "completed.",
                )

            return redirect(
                "billing:pricing"
            )

        # ----------------------------------------------------
        # Verify amount.
        # ----------------------------------------------------

        paid_amount = int(
            result.get(
                "total_amount",
                0,
            )
        )

        if paid_amount != checkout.price.amount:
            raise ValueError(
                "Khalti payment amount does not "
                "match the checkout price."
            )

        # ----------------------------------------------------
        # Finalize.
        # ----------------------------------------------------

        transaction_id = str(
            result.get(
                "transaction_id",
                "",
            )
        )

        if not transaction_id:
            raise ValueError(
                "Khalti did not return a "
                "transaction ID."
            )

        finalize_one_time_payment(
            checkout,
            provider_payment_id=(
                f"khalti:{transaction_id}"
            ),
            amount=(
                checkout.price.amount
            ),
            currency=(
                checkout.price.currency
            ),
            provider_response=result,
        )

        messages.success(
            request,
            "Payment successful. "
            "Your subscription is now active.",
        )

        return redirect(
            "billing:success"
        )

    except Exception:

        logger.exception(
            "Khalti callback failed."
        )

        messages.error(
            request,
            "We could not confirm your "
            "Khalti payment.",
        )

        return redirect(
            "billing:pricing"
        )

# ============================================================
# eSewa callback
# ============================================================

@csrf_exempt
@require_GET
def esewa_callback(
    request: HttpRequest,
) -> HttpResponse:

    encoded = request.GET.get(
        "data",
        "",
    )

    if not encoded:

        messages.error(
            request,
            "No eSewa payment response was received.",
        )

        return redirect(
            "billing:dashboard"
        )

    try:

        data = verify_esewa_response(
            encoded
        )

        transaction_uuid = data.get(
            "transaction_uuid"
        )

        if not transaction_uuid:
            raise ValueError(
                "eSewa response has no transaction UUID."
            )

        session = get_object_or_404(
            CheckoutSession,
            provider=Provider.ESEWA,
            provider_session_id=transaction_uuid,
        )

        expected_amount = (
            Decimal(session.price.amount)
            / Decimal("100")
        )

        received_amount = Decimal(
            str(
                data.get(
                    "total_amount"
                )
            )
        )

        verified = (
            data.get("status") == "COMPLETE"
            and data.get("product_code")
            == session.metadata.get(
                "product_code"
            )
            and received_amount
            == expected_amount
        )

        if verified:

            status_response = esewa_status(
                transaction_uuid,
                f"{expected_amount:.2f}",
            )

            verified = (
                status_response.get("status")
                == "COMPLETE"
            )

        payment_id = str(
            data.get("transaction_code")
            or transaction_uuid
        )

        Payment.objects.update_or_create(
            provider=Provider.ESEWA,
            provider_payment_id=payment_id,
            defaults={
                "tenant": session.tenant,
                "amount": session.price.amount,
                "currency": "NPR",
                "status": (
                    Payment.Status.SUCCEEDED
                    if verified
                    else Payment.Status.FAILED
                ),
                "paid_at": (
                    timezone.now()
                    if verified
                    else None
                ),
                "metadata": data,
            },
        )

        if verified:

            session.status = "complete"
            session.completed_at = (
                session.completed_at
                or timezone.now()
            )

            session.save(
                update_fields=[
                    "status",
                    "completed_at",
                ]
            )

            messages.success(
                request,
                "eSewa payment completed successfully.",
            )

        else:

            messages.error(
                request,
                "eSewa payment could not be verified.",
            )

    except Exception as exc:

        logger.exception(
            "eSewa callback processing failed."
        )

        messages.error(
            request,
            f"Unable to verify eSewa payment: {exc}",
        )

    return redirect(
        "billing:dashboard"
    )

@require_GET
def esewa_failure(
    request: HttpRequest,
) -> HttpResponse:

    data_b64 = request.GET.get("data")

    try:

        # eSewa may send response data even on failure.
        # We attempt to decode/verify it, but failure
        # handling must not provision anything.

        if data_b64:

            try:
                data = verify_esewa_response(
                    data_b64
                )

                transaction_uuid = str(
                    data.get(
                        "transaction_uuid",
                        "",
                    )
                )

            except Exception:
                logger.warning(
                    "Could not verify eSewa "
                    "failure callback.",
                    exc_info=True,
                )

                transaction_uuid = ""

            if transaction_uuid:

                checkout = (
                    CheckoutSession.objects
                    .filter(
                        provider=Provider.ESEWA,
                        provider_session_id=(
                            transaction_uuid
                        ),
                    )
                    .first()
                )

                if checkout:
                    mark_checkout_failed(
                        checkout,
                        reason=(
                            "Customer/payment "
                            "was not completed."
                        ),
                    )

    except Exception:
        logger.exception(
            "eSewa failure callback failed."
        )

    messages.info(
        request,
        "The eSewa payment was cancelled "
        "or did not complete.",
    )

    return redirect(
        "billing:pricing"
    )

@require_GET
def esewa_success(
    request: HttpRequest,
) -> HttpResponse:

    data_b64 = request.GET.get("data")

    try:

        # ----------------------------------------------------
        # 1. Verify eSewa's cryptographic signature.
        # ----------------------------------------------------

        data = verify_esewa_response(
            data_b64
        )

        transaction_uuid = str(
            data.get(
                "transaction_uuid",
                "",
            )
        )

        if not transaction_uuid:
            raise ValueError(
                "Missing eSewa transaction UUID."
            )

        # ----------------------------------------------------
        # 2. Find our checkout.
        # ----------------------------------------------------

        checkout = get_object_or_404(
            CheckoutSession,
            provider=Provider.ESEWA,
            provider_session_id=(
                transaction_uuid
            ),
        )

        # ----------------------------------------------------
        # 3. Validate callback against our DB.
        # ----------------------------------------------------

        validate_esewa_transaction(
            data,
            transaction_uuid=(
                transaction_uuid
            ),
            expected_amount=(
                checkout.price.amount
            ),
            product_code=(
                checkout.metadata.get(
                    "product_code"
                )
            ),
        )

        # ----------------------------------------------------
        # 4. Ask eSewa directly.
        #
        # Never provision solely because the browser
        # returned with status=COMPLETE.
        # ----------------------------------------------------

        status_response = esewa_status(
            transaction_uuid=(
                transaction_uuid
            ),
            total_amount=(
                checkout.metadata[
                    "total_amount"
                ]
            ),
        )

        status = str(
            status_response.get(
                "status",
                "",
            )
        ).upper()

        if status != "COMPLETE":
            mark_checkout_failed(
                checkout,
                reason=(
                    "eSewa status was "
                    f"{status}"
                ),
            )

            messages.error(
                request,
                "The eSewa payment could not "
                "be confirmed.",
            )

            return redirect(
                "billing:pricing"
            )

        # ----------------------------------------------------
        # 5. Finalize.
        # ----------------------------------------------------

        ref_id = (
            status_response.get(
                "refId"
            )
            or status_response.get(
                "ref_id"
            )
            or data.get(
                "transaction_code"
            )
            or transaction_uuid
        )

        finalize_one_time_payment(
            checkout,
            provider_payment_id=(
                f"esewa:{ref_id}"
            ),
            amount=(
                checkout.price.amount
            ),
            currency=(
                checkout.price.currency
            ),
            provider_response={
                "callback": data,
                "status": status_response,
            },
        )

        messages.success(
            request,
            "Payment successful. "
            "Your subscription is now active.",
        )

        return redirect(
            "billing:success"
        )

    except Exception as exc:

        logger.exception(
            "eSewa success callback failed."
        )

        messages.error(
            request,
            "We could not confirm your "
            "eSewa payment.",
        )

        return redirect(
            "billing:pricing"
        )

    
# ============================================================
# Stripe Webhook
# ============================================================
@csrf_exempt
@require_POST
def stripe_webhook(request: HttpRequest) -> HttpResponse:
    """
    Validates the Stripe signature, deduplicates and persists the raw webhook payload,
    and defers processing (sending emails, database updates) to a Celery task.
    """
    signature = request.headers.get("Stripe-Signature", "")

    if not signature:
        logger.error("Stripe webhook rejected: missing Stripe-Signature header.")
        return HttpResponse("Missing Stripe-Signature header", status=400)

    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        logger.critical("Stripe webhook rejected: STRIPE_WEBHOOK_SECRET is not configured.")
        return HttpResponse("Stripe webhook is not configured", status=500)

    # 1. Verify signature and parse raw body safe from dict conversion errors
    try:
        stripe.Webhook.construct_event(
            request.body,
            signature,
            webhook_secret,
        )
        event_data = json.loads(request.body.decode("utf-8"))
    except ValueError:
        logger.exception("Invalid Stripe webhook payload.")
        return HttpResponse("Invalid payload", status=400)
    except stripe.SignatureVerificationError:
        logger.exception("Invalid Stripe webhook signature.")
        return HttpResponse("Invalid signature", status=400)
    except Exception:
        logger.exception("Unexpected error while validating Stripe webhook.")
        return HttpResponse("Webhook validation failed", status=400)

    event_id = str(event_data.get("id") or "")
    event_type = str(event_data.get("type") or "")

    if not event_id or not event_type:
        logger.error("Stripe webhook missing event ID/type.")
        return HttpResponse("Invalid Stripe event structure", status=400)

    # 2. Persist event & queue background task inside an atomic transaction
    with transaction.atomic():
        webhook, created = WebhookEvent.objects.get_or_create(
            provider=Provider.STRIPE,
            event_id=event_id,
            defaults={
                "event_type": event_type,
                "payload": event_data,
                "processed": False,
                "error": "",
            },
        )

        # Idempotency check: ignore duplicate webhooks already processed
        if not created and webhook.processed:
            logger.info("Stripe webhook already processed: event_id=%s", event_id)
            return HttpResponse(status=200)

        # Update event record if re-delivered
        if not created:
            webhook.event_type = event_type
            webhook.payload = event_data
            webhook.error = ""
            webhook.save(update_fields=["event_type", "payload", "error"])

        # Trigger Celery task after DB transaction successfully commits
        transaction.on_commit(
            lambda: process_stripe_webhook_task.delay(webhook.pk)
        )

    return HttpResponse(status=200)

