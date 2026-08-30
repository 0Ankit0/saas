from .models import User

def total_users_count() -> int:
    return User.objects.filter(is_active=True).count()