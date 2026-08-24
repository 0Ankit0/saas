from saas.billing.models import Subscription
from saas.billing.services.stripe import get_current_subscription

def has_feature(
    tenant,
    feature_key: str,
) -> bool:

    subscription = get_current_subscription(
        tenant
    )

    if not subscription:
        return False

    return (
        subscription
        .price
        .product
        .product_features
        .filter(
            feature__key=feature_key,
            feature__active=True,
            enabled=True,
        )
        .exists()
    )


def get_current_subscription(
    tenant,
) -> Subscription | None:

    return (
        Subscription.objects
        .select_related(
            "price__product",
            "customer",
        )
        .filter(
            tenant=tenant,
            status__in=[
                Subscription.Status.ACTIVE,
                Subscription.Status.TRIALING,
                Subscription.Status.PAST_DUE,
            ],
        )
        .order_by("-created_at")
        .first()
    )