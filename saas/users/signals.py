from allauth.account.signals import (
    email_changed,
    email_confirmed,
)
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from saas.users.tasks import process_avatar

from .models import User


@receiver(email_confirmed)
def on_email_confirmed(
    request,
    email_address,
    **kwargs,
):
    User.objects.filter(
        pk=email_address.user_id,
    ).update(
        email=email_address.email,
        is_verified=True,
    )


@receiver(email_changed)
def on_email_changed(
    request,
    user,
    from_email_address,
    to_email_address,
    **kwargs,
):
    User.objects.filter(
        pk=user.pk,
    ).update(
        email=to_email_address.email,
        is_verified=False,
    )


@receiver(pre_save, sender=User)
def track_avatar_change(sender, instance: User, **kwargs):
    if not instance.pk:
        instance._avatar_changed = bool(instance.avatar)
        return

    previous = sender.objects.filter(pk=instance.pk).only("avatar").first()

    previous_avatar = previous.avatar.name if previous else None
    current_avatar = instance.avatar.name if instance.avatar else None

    instance._avatar_changed = previous_avatar != current_avatar

@receiver(post_save, sender=User)
def queue_avatar_processing(sender, instance: User, **kwargs):
    if not getattr(instance, "_avatar_changed", False) or not instance.avatar:
        return
    transaction.on_commit(lambda: process_avatar.delay(instance.pk, instance.avatar.name))