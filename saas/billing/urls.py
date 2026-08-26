from django.urls import path, include
from . import views


app_name = "billing"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("pricing/", views.pricing, name="pricing"),
    path("checkout/<int:price_id>/", views.checkout, name="checkout"),
    path("portal/", views.portal, name="portal"),
    path("cancel/", views.cancel, name="cancel"),
    path("success/", views.success, name="success"),
    path("callback/khalti/", views.khalti_callback, name="khalti-callback"),
    path("callback/esewa/", views.esewa_callback, name="esewa-callback"),
    path(
        "callback/esewa/success/",
        views.esewa_success,
        name="esewa_success",
    ),

    path(
        "callback/esewa/failure/",
        views.esewa_failure,
        name="esewa_failure",
    ),
    path("webhooks/stripe/", views.stripe_webhook, name="stripe-webhook"),
]