from django.apps import AppConfig


class BillingConfig(AppConfig):
    name = 'saas.billing'

    def ready(self):
        import saas.billing.signals  # noqa: F401
