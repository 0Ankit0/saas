from django.core.management.base import BaseCommand
from django.db.models import Q

from saas.billing.models import Price
from saas.billing.models import Product
from saas.billing.services.stripe import create_stripe_product, create_stripe_price


class Command(BaseCommand):
    help = "Create missing Stripe products and prices for the local billing catalog."

    def handle(self, *args, **options):
        for product in Product.objects.all().order_by("pk"):
            if not product.provider_product_id:
                product_data = create_stripe_product(product)
                if product_data:
                    self.stdout.write(self.style.SUCCESS(f"Created Stripe product {product_data.id} for {product.slug}"))
            for price in Price.objects.filter(
                Q(provider_price_id__isnull=True) | Q(provider_price_id=""),
                product=product
            ).order_by("pk"):
                price_data = create_stripe_price(price)
                if price_data:
                    self.stdout.write(self.style.SUCCESS(f"Created Stripe price {price_data.id} for {price}"))
