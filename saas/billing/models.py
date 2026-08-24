# billing/models.py

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class Provider(models.TextChoices):
    STRIPE = "stripe", _("Stripe")
    KHALTI = "khalti", _("Khalti")
    ESEWA = "esewa", _("eSewa")


class Product(models.Model):
    name = models.CharField(_("Name"), max_length=255)
    slug = models.SlugField(_("Slug"), unique=True)
    description = models.TextField(
        _("Description"),
        blank=True,
    )

    active = models.BooleanField(
        default=True,
    )

    provider_product_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        editable=False,
        unique=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_products",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Currency(models.TextChoices):
    NPR = "NPR", _("Nepalese Rupee")
    USD = "USD", _("US Dollar")


class Price(models.Model):

    class Interval(models.TextChoices):
        ONE_TIME = "one_time", _("One Time")
        DAY = "day", _("Daily")
        MONTH = "month", _("Monthly")
        YEAR = "year", _("Yearly")

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="prices",
    )

    name = models.CharField(
        max_length=255,
        blank=True,
    )

    amount = models.PositiveBigIntegerField(
        help_text=_(
            "Amount in the smallest currency unit."
        ),
    )

    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.NPR,
    )

    interval = models.CharField(
        max_length=20,
        choices=Interval.choices,
        default=Interval.MONTH,
    )

    interval_count = models.PositiveIntegerField(
        default=1,
    )

    active = models.BooleanField(
        default=True,
    )

    provider_price_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        editable=False,
        unique=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_prices",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "product__name",
            "amount",
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    interval_count__gte=1
                ),
                name=(
                    "billing_price_interval_count_positive"
                ),
            ),
        ]

    @property
    def is_recurring(self):
        return (
            self.interval
            != self.Interval.ONE_TIME
        )

    @property
    def amount_decimal(self):
        return (
            Decimal(self.amount)
            / Decimal("100")
        )

    @property
    def amount_display(self):
        return (
            f"{self.amount_decimal:.2f} "
            f"{self.currency.upper()}"
        )

    def __str__(self):
        suffix = (
            ""
            if self.interval
            == self.Interval.ONE_TIME
            else f" / {self.interval}"
        )

        return (
            f"{self.product.name} - "
            f"{self.amount_decimal:.2f} "
            f"{self.currency.upper()}"
            f"{suffix}"
        )


class Feature(models.Model):
    key = models.SlugField(
        unique=True,
    )

    name = models.CharField(
        max_length=255,
    )

    description = models.TextField(
        blank=True,
    )

    active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_features",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_features",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductFeature(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product_features",
    )

    feature = models.ForeignKey(
        Feature,
        on_delete=models.CASCADE,
        related_name="product_features",
    )

    enabled = models.BooleanField(
        default=True,
    )

    limit = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_product_features",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_product_features",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "product",
                    "feature",
                ],
                name="billing_product_feature_unique",
            ),
        ]

    def __str__(self):
        return f"{self.product}: {self.feature}"


class BillingCustomer(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="billing_customers",
    )

    provider = models.CharField(
        max_length=32,
        choices=Provider.choices,
    )

    provider_customer_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        editable=False,
    )

    email = models.EmailField()
    name = models.CharField(
        max_length=255,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_billing_customers",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_billing_customers",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "tenant",
                    "provider",
                ],
                name=(
                    "billing_customer_tenant_provider_unique"
                ),
            ),
            models.UniqueConstraint(
                fields=[
                    "provider",
                    "provider_customer_id",
                ],
                condition=models.Q(
                    provider_customer_id__isnull=False
                ),
                name=(
                    "billing_customer_provider_id_unique"
                ),
            ),
        ]

    def __str__(self):
        return (
            self.name
            or self.email
            or str(self.tenant)
        )


class Subscription(models.Model):

    class Status(models.TextChoices):
        INCOMPLETE = "incomplete", _("Incomplete")
        TRIALING = "trialing", _("Trialing")
        ACTIVE = "active", _("Active")
        PAST_DUE = "past_due", _("Past due")
        CANCELED = "canceled", _("Canceled")
        UNPAID = "unpaid", _("Unpaid")
        PAUSED = "paused", _("Paused")

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )

    price = models.ForeignKey(
        Price,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
    )

    provider = models.CharField(
        max_length=32,
        choices=Provider.choices,
    )

    provider_subscription_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        editable=False,
        unique=True,
    )

    customer = models.ForeignKey(
        BillingCustomer,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )

    current_period_start = models.DateTimeField(
        null=True,
        blank=True,
    )

    current_period_end = models.DateTimeField(
        null=True,
        blank=True,
    )

    cancel_at_period_end = models.BooleanField(
        default=False,
    )

    canceled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    trial_end = models.DateTimeField(
        null=True,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "tenant",
                    "price",
                ],
                condition=models.Q(
                    status="active"
                ),
                name=(
                    "billing_subscription_single_active_per_price"
                ),
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "tenant",
                    "status",
                ]
            ),
            models.Index(
                fields=[
                    "provider",
                    "provider_subscription_id",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"{self.tenant} - "
            f"{self.price.product} "
            f"({self.status})"
        )


class Invoice(models.Model):

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        OPEN = "open", _("Open")
        PAID = "paid", _("Paid")
        VOID = "void", _("Void")
        UNCOLLECTIBLE = (
            "uncollectible",
            _("Uncollectible"),
        )

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="billing_invoices",
    )

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )

    provider = models.CharField(
        max_length=32,
        choices=Provider.choices,
    )

    provider_invoice_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        editable=False,
        unique=True,
    )

    number = models.CharField(
        max_length=255,
        blank=True,
    )

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
    )

    amount_due = models.PositiveBigIntegerField(
        default=0,
    )

    amount_paid = models.PositiveBigIntegerField(
        default=0,
    )

    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.NPR,
    )

    hosted_invoice_url = models.URLField(
        blank=True,
    )

    invoice_pdf = models.URLField(
        blank=True,
    )

    period_start = models.DateTimeField(
        null=True,
        blank=True,
    )

    period_end = models.DateTimeField(
        null=True,
        blank=True,
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )
    @property
    def amount_due_decimal(self) -> Decimal:
        return Decimal(self.amount_due) / Decimal("100")

    @property
    def amount_due_display(self) -> str:
        return f"{self.amount_due_decimal:.2f} {self.currency.upper()}"

    @property
    def amount_paid_decimal(self) -> Decimal:
        return Decimal(self.amount_paid) / Decimal("100")

    @property
    def amount_paid_display(self) -> str:
        return f"{self.amount_paid_decimal:.2f} {self.currency.upper()}"
    

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "provider",
                    "provider_invoice_id",
                ],
                name=(
                    "billing_invoice_provider_id_unique"
                ),
            ),
        ]


class Payment(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SUCCEEDED = "succeeded", _("Succeeded")
        FAILED = "failed", _("Failed")
        REFUNDED = "refunded", _("Refunded")
        PARTIALLY_REFUNDED = (
            "partially_refunded",
            _("Partially refunded"),
        )

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="payments",
    )

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )

    amount = models.PositiveBigIntegerField()

    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.NPR,
    )

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
    )

    provider = models.CharField(
        max_length=32,
        choices=Provider.choices,
    )

    provider_payment_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        editable=False,
        unique=True,
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    @property
    def amount_decimal(self) -> Decimal:
        return Decimal(self.amount) / Decimal("100")

    @property
    def amount_display(self) -> str:
        return f"{self.amount_decimal:.2f} {self.currency.upper()}"


class CheckoutSession(models.Model):

    class Mode(models.TextChoices):
        PAYMENT = "payment", _("Payment")
        SUBSCRIPTION = (
            "subscription",
            _("Subscription"),
        )

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="checkout_sessions",
    )

    price = models.ForeignKey(
        Price,
        on_delete=models.PROTECT,
        related_name="checkout_sessions",
    )

    provider = models.CharField(
        max_length=32,
        choices=Provider.choices,
    )

    provider_session_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        editable=False,
        unique=True,
    )

    mode = models.CharField(
        max_length=32,
    )

    status = models.CharField(
        max_length=32,
        default="open",
    )

    url = models.URLField(
        max_length=2048,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )


class WebhookEvent(models.Model):
    provider = models.CharField(
        max_length=32,
        choices=Provider.choices,
    )

    event_id = models.CharField(
        max_length=255,
    )

    event_type = models.CharField(
        max_length=255,
    )

    payload = models.JSONField()

    processed = models.BooleanField(
        default=False,
    )

    processing = models.BooleanField(
        default=False,
    )

    processed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    attempts = models.PositiveIntegerField(
        default=0,
    )

    error = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "provider",
                    "event_id",
                ],
                name=(
                    "billing_webhook_provider_event_unique"
                ),
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "event_type",
                    "processed",
                ]
            ),
            models.Index(
                fields=[
                    "processing",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"{self.provider}: "
            f"{self.event_type}: "
            f"{self.event_id}"
        )