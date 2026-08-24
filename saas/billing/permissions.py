from collections.abc import Callable
from functools import wraps
from typing import Any

from django.http import HttpRequest
from django.shortcuts import redirect
from django.contrib import messages

from .utils import has_feature


def requires_feature(feature_key: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(view_func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            if not request.user.is_authenticated or not has_feature(request.tenant, feature_key):
                messages.error(request, "Your current plan does not include this feature.")
                return redirect("billing:pricing")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
