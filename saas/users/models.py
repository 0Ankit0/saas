from typing import ClassVar
from django.contrib.auth.models import AbstractUser
from django.db.models import CharField
from django.db.models import EmailField
from django.db import models
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill, Transpose
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from saas.users.managers import UserManager

from tenant_users.tenants.models import UserProfile

class User(UserProfile):
    """
    Default custom user model for saas.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    name = CharField(_("Name of User"), blank=True, max_length=255)
    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
    )

    avatar_thumbnail = ImageSpecField(
        source="avatar",
        processors=[
            Transpose(),
            ResizeToFill(200, 200),
        ],
        format="WEBP",
        options={
            "quality": 80,
        },
    )
    bio = models.TextField(
        blank=True,
    )

    timezone = models.CharField(
        max_length=50,
        default="UTC",
    )

    language = models.CharField(
        max_length=10,
        default="en",
    )

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"pk": self.pk})