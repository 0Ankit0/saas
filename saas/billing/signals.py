from typing import cast

from celery import Task
from django.db.models.signals import post_save
from django.dispatch import receiver

from saas.billing.tasks import create_stripe_customer_task, create_stripe_price_task, create_stripe_product_task
from .models import BillingCustomer, Product, Price

@receiver(post_save, sender=Product)
def product_post_save(sender, instance, created, **kwargs):
    if created:
        task_obj = cast(Task, create_stripe_product_task)
        task_obj.delay(instance.pk)   

@receiver(post_save, sender=Price)
def price_post_save(sender, instance, created, **kwargs):
    if created:
        task_obj = cast(Task, create_stripe_price_task)
        task_obj.delay(instance.pk)

@receiver(post_save, sender=BillingCustomer)
def billing_customer_post_save(sender, instance, created, **kwargs):
    # if created:
    task_obj = cast(Task, create_stripe_customer_task)
    task_obj.delay(instance.pk)
