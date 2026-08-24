import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

from django.conf import settings

from .models import Provider


@dataclass(frozen=True)
class GatewayResult:
    provider: str
    reference: str
    redirect_url: str = ""
    form_action: str = ""
    form_fields: dict[str, str] | None = None
    metadata: dict[str, str] | None = None


def _json_request(url: str, payload: dict, headers: dict[str, str]) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:  # noqa: S310
        return json.loads(response.read().decode())


def _required_setting(name: str) -> str:
    value = str(getattr(settings, name, "") or "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured.")
    return value


def _khalti_secret() -> str:
    return _required_setting("KHALTI_SECRET_KEY")   


def _khalti_base() -> str:
    return _required_setting("KHALTI_BASE_URL")
    # return "https://dev.khalti.com/api/v2" if settings.KHALTI_ENVIRONMENT == "sandbox" else "https://khalti.com/api/v2"


def create_khalti_checkout(request, price) -> GatewayResult:
    if price.currency.lower() != "npr":
        raise ValueError("Khalti checkout requires an NPR price.")
    if price.is_recurring:
        raise ValueError("Khalti is configured for one-time checkout; use Stripe for recurring subscriptions.")

    order_id = f"T{request.tenant.pk}-{uuid.uuid4().hex[:20]}"
    callback = request.build_absolute_uri("/billing/callback/khalti/")
    payload = {
        "return_url": callback,
        "website_url": request.build_absolute_uri("/"),
        "amount": str(price.amount),
        "purchase_order_id": order_id,
        "purchase_order_name": price.product.name[:255],
        "customer_info": {
            "name": getattr(request.user, "name", "") or str(request.user),
            "email": getattr(request.user, "email", ""),
            "phone": getattr(request.user, "phone", "") or "",
        },
    }
    response = _json_request(
        f"{_khalti_base()}/epayment/initiate/",
        payload,
        {"Authorization": f"Key {_khalti_secret()}"},
    )
    return GatewayResult(
        Provider.KHALTI,
        str(response["pidx"]),
        redirect_url=str(response["payment_url"]),
        metadata={"purchase_order_id": order_id},
    )


def khalti_lookup(pidx: str) -> dict:
    if not pidx:
        raise ValueError("Khalti payment reference is required.")
    return _json_request(
        f"{_khalti_base()}/epayment/lookup/",
        {"pidx": pidx},
        {"Authorization": f"Key {_khalti_secret()}"},
    )


def _esewa_secret() -> str:
    return _required_setting("ESEWA_SECRET_KEY")


def _esewa_product_code() -> str:
    return _required_setting("ESEWA_PRODUCT_CODE")


def _esewa_secret_message(total_amount: str, transaction_uuid: str, product_code: str) -> str:
    return f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"


def _esewa_signature(message: str) -> str:
    digest = hmac.new(_esewa_secret().encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _esewa_base() -> str:
    return _required_setting("ESEWA_BASE_URL")
    # return "https://rc-epay.esewa.com.np/api/epay/main/v2/form" if settings.ESEWA_ENVIRONMENT == "sandbox" else "https://epay.esewa.com.np/api/epay/main/v2/form"


def create_esewa_checkout(request, price) -> GatewayResult:
    if price.currency.lower() != "npr":
        raise ValueError("eSewa checkout requires an NPR price.")
    if price.is_recurring:
        raise ValueError("eSewa is configured for one-time checkout; use Stripe for recurring subscriptions.")

    transaction_uuid = f"T-{request.tenant.pk}-{uuid.uuid4().hex[:20]}"
    total = f"{Decimal(price.amount) / Decimal('100'):.2f}"
    product_code = _esewa_product_code()
    signed_field_names = "total_amount,transaction_uuid,product_code"
    callback = request.build_absolute_uri("/billing/callback/esewa/")
    fields = {
        "amount": total,
        "tax_amount": "0",
        "total_amount": total,
        "transaction_uuid": transaction_uuid,
        "product_code": product_code,
        "product_service_charge": "0",
        "product_delivery_charge": "0",
        "success_url": callback,
        "failure_url": callback,
        "signed_field_names": signed_field_names,
        "signature": _esewa_signature(_esewa_secret_message(total, transaction_uuid, product_code)),
    }
    return GatewayResult(
        Provider.ESEWA,
        transaction_uuid,
        form_action=_esewa_base(),
        form_fields=fields,
        metadata={"product_code": product_code},
    )


def verify_esewa_response(data_b64: str) -> dict:
    try:
        raw = base64.b64decode(data_b64, validate=True).decode()
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid eSewa response.") from exc

    signed_names = data.get("signed_field_names", "")
    if not signed_names or "signature" not in data:
        raise ValueError("Incomplete eSewa response.")
    values = []
    for name in signed_names.split(","):
        if name not in data:
            raise ValueError("Incomplete eSewa response.")
        values.append(f"{name}={data[name]}")
    expected = _esewa_signature(",".join(values))
    if not hmac.compare_digest(expected, data.get("signature", "")):
        raise ValueError("Invalid eSewa response signature.")
    return data


def esewa_status(transaction_uuid: str, total_amount: str) -> dict:
    base = "https://rc.esewa.com.np/api/epay/transaction/status/" if settings.ESEWA_ENVIRONMENT == "sandbox" else "https://epay.esewa.com.np/api/epay/transaction/status/"
    query = urlencode({"product_code": _esewa_product_code(), "total_amount": total_amount, "transaction_uuid": transaction_uuid})
    request = Request(f"{base}?{query}", method="GET")
    with urlopen(request, timeout=20) as response:  # noqa: S310
        return json.loads(response.read().decode())
