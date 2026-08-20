from django.contrib import admin
from slugify import slugify
from unfold.admin import ModelAdmin

from saas.billing.models import BillingCustomer, CheckoutSession, Feature, Product, Price, ProductFeature, Subscription, Payment, Invoice, WebhookEvent


# Register your models here.
@admin.register(Product)
class ProductAdmin(ModelAdmin):

    list_display = [
        "name",
        "slug",
        "active",
        "provider_product_id",
        "created_at",
        "updated_at",
    ]

    search_fields = [
        "name",
        "slug",
        "provider_product_id",
    ]
    readonly_fields = [
        "provider_product_id",
        "created_by"
    ]

    fields = (
        "name",
        "description",
        "active",
        "metadata",
    )
    def save_model(self, request, obj, form, change):
        if not obj.provider_product_id:
            pass 
        obj.slug = slugify(obj.name)
        obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(Price)
class PriceAdmin(ModelAdmin):
    list_display = [
        "name",
        "amount_display",
        "currency",
        "interval",
        "created_at",
    ]

    search_fields = [
        "amount",
        "currency",
        "interval",
    ]
    readonly_fields = [
        "created_by"
    ]

@admin.register(Feature)
class FeatureAdmin(ModelAdmin):
    list_display = [
        "key",
        "name",
        "active",
        "created_at",
        "updated_at",
    ]
    search_fields = [
        "key",
        "name",
    ]
    fields = (
        "name",
        "description",
        "active",
    )
    def save_model(self, request, obj, form, change):
        if change:
            obj.updated_by = request.user
        else:
            obj.created_by = request.user
            obj.key = slugify(obj.name)
        super().save_model(request, obj, form, change)

@admin.register(ProductFeature)
class ProductFeatureAdmin(ModelAdmin):
    list_display = [
        "product",
        "feature",
        "enabled",
        "created_at",
        "updated_at",
    ]
    search_fields = [
        "product__name",
        "feature__name",
    ]
    fields = (
        "product",
        "feature",
        "enabled",
    )
    autocomplete_fields = [
        "product",
        "feature",
    ]
    
    def save_model(self, request, obj, form, change):
        if change:
            obj.updated_by = request.user
        else:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(BillingCustomer)
class BillingCustomerAdmin(ModelAdmin):
    list_display = [
        "name",
        "email",
        "tenant",
        "created_at",
    ]
    search_fields = [
        "name",
        "email",
    ]
    fields = (
        "tenant",
        "provider",
        "name",
        "email",
    )
    autocomplete_fields = [
        "tenant",
    ]
    readonly_fields = [
        "provider_customer_id",
    ]
    def save_model(self, request, obj, form, change):
        if change:
            obj.updated_by = request.user
        else:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_display = [
        "tenant",
        "provider",
        "customer",
        "price",
        "status",
        "current_period_start",
        "current_period_end",
        "created_at",
    ]
    search_fields = [
        "tenant__name",
        "price__name",
    ]
    fields = (
        "tenant",
        "provider",
        "customer",
        "price",
        "status",
        "current_period_start",
        "current_period_end",
        "trial_end",
    )
    autocomplete_fields = [
        "tenant",
        "customer",
        "price",
    ]

@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = [
        "tenant",
        "provider",
        "subscription",
        "amount_display",
        "status",
        "created_at",
    ]
    search_fields = [
        "tenant__name",
    ]
    fields = (
        "tenant",
        "provider",
        "subscription",
        "amount",
        "currency",
        "status",
        "metadata",
    )
    autocomplete_fields = [
        "tenant",
        "subscription",
    ]

@admin.register(Invoice)
class InvoiceAdmin(ModelAdmin):
    list_display = [
        "tenant",
        "provider",
        "subscription",
        "amount_due_display",
        "amount_paid_display",
        "status",
        "created_at",
    ]
    search_fields = [
        "tenant__name",
    ]
    # fields = (
    #     "tenant",
    #     "provider",
    #     "subscription",
    #     "amount_due",
    #     "amount_paid",
    #     "period_start",
    #     "period_end",
    #     "currency",
    #     "status",
    #     "metadata",
    # )
    autocomplete_fields = [
        "tenant",
        "subscription",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(CheckoutSession)
class CheckoutSessionAdmin(ModelAdmin):
    list_display = [
        "tenant",
        "price",
        "provider",
        "mode",
        "status",
        "completed_at",
    ]
    search_fields = [
        "tenant__name",
        "price__name",
    ]
    fields = (
        "tenant",
        "price",
        "provider",
        "mode",
        "status",
        "metadata",
    )
    autocomplete_fields = [
        "tenant",
        "price",
    ]

    def save_model(self, request, obj, form, change):
        if change:
            obj.updated_by = request.user
        else:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(WebhookEvent)
class WebhookEventAdmin(ModelAdmin):
    list_display = [
        "provider",
        "event_type",
        "processed",
        "processed_at",
        "created_at",
    ]
    search_fields = [
        "provider",
        "event_type",
    ]
    list_filter = [
        "processed",
    ]
    # fields = (
    #     "provider",
    #     "event_type",
    #     "payload",
    # )
    # readonly_fields = [
    #     "provider",
    #     "event_type",
    #     "payload",
    #     "created_at",
    # ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False