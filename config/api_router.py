from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from saas.users.api.views import UserViewSet
from saas.tenants.api.views import TenantViewSet, DomainViewSet, InvitationViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("tenants", TenantViewSet)
router.register("domains", DomainViewSet)
router.register("invitations", InvitationViewSet)

app_name = "api"
urlpatterns = router.urls
