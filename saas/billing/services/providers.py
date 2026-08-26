# billing/services/provider.py

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from rest_framework.generics import get_object_or_404

from ..models import BillingCustomer, Provider


@dataclass(frozen=True)
class GatewayResult:
    provider: str
    reference: str
    redirect_url: str = ""
    form_action: str = ""
    form_fields: dict[str, str] | None = None
    metadata: dict[str, str] | None = None

# ============================================================
# Billing Customer
# ============================================================
def _get_billing_customer(request) -> BillingCustomer:
    customer = get_object_or_404(
    BillingCustomer,
    tenant=request.tenant,
    active=True,
)

    if not customer:
        raise RuntimeError(
            "No billing customer exists for this tenant."
        )

    if not customer.email:
        raise RuntimeError(
            "Billing customer email is not configured."
        )

    if not customer.name:
        raise RuntimeError(
            "Billing customer name is not configured."
        )

    return customer

# ============================================================
# HTTP
# ============================================================


def _json_request(
    url: str,
    payload: dict,
    headers: dict[str, str],
) -> dict:

    request = Request(
        url,
        data=json.dumps(
            payload
        ).encode("utf-8"),
        headers={
            **headers,
            "Content-Type": (
                "application/json"
            ),
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=20,
        ) as response:
            body = (
                response
                .read()
                .decode("utf-8")
            )

    except HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"Payment provider returned "
            f"HTTP {exc.code}: {body}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            "Unable to connect to payment provider: "
            f"{exc.reason}"
        ) from exc

    try:
        result = json.loads(body)

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Payment provider returned invalid JSON."
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError(
            "Payment provider returned an invalid response."
        )

    return result


def _json_get(
    url: str,
) -> dict:

    request = Request(
        url,
        headers={
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(
            request,
            timeout=20,
        ) as response:
            body = (
                response
                .read()
                .decode("utf-8")
            )

    except HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"Payment provider returned "
            f"HTTP {exc.code}: {body}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            "Unable to connect to payment provider: "
            f"{exc.reason}"
        ) from exc

    try:
        result = json.loads(body)

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Payment provider returned invalid JSON."
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError(
            "Payment provider returned an invalid response."
        )

    return result


def _required_setting(
    name: str,
) -> str:

    value = str(
        getattr(
            settings,
            name,
            "",
        )
        or ""
    ).strip()

    if not value:
        raise RuntimeError(
            f"{name} is not configured."
        )

    return value


# ============================================================
# KHALTI
# ============================================================


def _khalti_secret() -> str:
    return _required_setting(
        "KHALTI_SECRET_KEY"
    )


def _khalti_base() -> str:
    return _required_setting(
        "KHALTI_BASE_URL"
    ).rstrip("/")


def create_khalti_checkout(request, price) -> GatewayResult:
    if price.currency.upper() != "NPR":
        raise ValueError(
            "Khalti checkout requires an NPR price."
        )

    if price.is_recurring:
        raise ValueError(
            "Khalti is configured for one-time checkout; "
            "use Stripe for recurring subscriptions."
        )

    customer = _get_billing_customer(request)

    order_id = (
        f"T{request.tenant.pk}-"
        f"{uuid.uuid4().hex[:20]}"
    )

    callback = request.build_absolute_uri(
        "/billing/callback/khalti/"
    )

    payload = {
        "return_url": callback,
        "website_url": request.build_absolute_uri("/"),
        "amount": str(price.amount),
        "purchase_order_id": order_id,
        "purchase_order_name": price.product.name[:255],
        "customer_info": {
            "name": customer.name,
            "email": customer.email,
            "phone": getattr(customer, "phone", "") or "",
        },
    }

    response = _json_request(
        f"{_khalti_base()}/epayment/initiate/",
        payload,
        {
            "Authorization": (
                f"Key {_khalti_secret()}"
            ),
        },
    )

    return GatewayResult(
        Provider.KHALTI,
        str(response["pidx"]),
        redirect_url=str(response["payment_url"]),
        metadata={
            "purchase_order_id": order_id,
            "billing_customer_id": str(customer.pk),
            "customer_email": customer.email,
            "customer_name": customer.name,
        },
    )

def khalti_lookup(
    pidx: str,
) -> dict:

    if not pidx:
        raise ValueError(
            "Khalti pidx is required."
        )

    return _json_request(
        f"{_khalti_base()}/epayment/lookup/",
        {
            "pidx": pidx,
        },
        {
            "Authorization": (
                f"Key {_khalti_secret()}"
            ),
        },
    )


# ============================================================
# eSEWA
# ============================================================


def _esewa_secret() -> str:
    return _required_setting(
        "ESEWA_SECRET_KEY"
    )


def _esewa_product_code() -> str:
    return _required_setting(
        "ESEWA_PRODUCT_CODE"
    )


def _esewa_environment() -> str:

    value = str(
        getattr(
            settings,
            "ESEWA_ENVIRONMENT",
            "sandbox",
        )
        or "sandbox"
    ).lower().strip()

    if value not in {
        "sandbox",
        "production",
    }:
        raise RuntimeError(
            "ESEWA_ENVIRONMENT must be "
            "'sandbox' or 'production'."
        )

    return value


def _esewa_form_url() -> str:

    if _esewa_environment() == "sandbox":
        return (
            "https://rc-epay.esewa.com.np"
            "/api/epay/main/v2/form"
        )

    return (
        "https://epay.esewa.com.np"
        "/api/epay/main/v2/form"
    )


def _esewa_status_url() -> str:

    if _esewa_environment() == "sandbox":
        return (
            "https://uat.esewa.com.np"
            "/api/epay/transaction/status/"
        )

    return (
        "https://epay.esewa.com.np"
        "/api/epay/transaction/status/"
    )


def _esewa_signature(
    message: str,
) -> str:

    digest = hmac.new(
        _esewa_secret().encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    return base64.b64encode(
        digest
    ).decode("ascii")


def _esewa_secret_message(
    total_amount: str,
    transaction_uuid: str,
    product_code: str,
) -> str:

    return (
        f"total_amount={total_amount},"
        f"transaction_uuid={transaction_uuid},"
        f"product_code={product_code}"
    )


def _esewa_amount(price) -> str:

    try:
        amount = (
            Decimal(str(price.amount))
            / Decimal("100")
        ).quantize(
            Decimal("0.01")
        )

    except (
        InvalidOperation,
        ValueError,
    ) as exc:
        raise ValueError(
            "Invalid eSewa amount."
        ) from exc

    if amount <= 0:
        raise ValueError(
            "eSewa amount must be greater than zero."
        )

    return f"{amount:.2f}"


def create_esewa_checkout(request, price) -> GatewayResult:
    if price.currency.upper() != "NPR":
        raise ValueError(
            "eSewa checkout requires an NPR price."
        )

    if price.is_recurring:
        raise ValueError(
            "eSewa is configured for one-time checkout; "
            "use Stripe for recurring subscriptions."
        )

    customer = _get_billing_customer(request)

    transaction_uuid = (
        f"T-{request.tenant.pk}-"
        f"{uuid.uuid4().hex[:20]}"
    )

    total = (
        Decimal(price.amount) / Decimal("100")
    ).quantize(Decimal("0.01"))

    total_str = f"{total:.2f}"

    product_code = _esewa_product_code()

    signed_field_names = (
        "total_amount,"
        "transaction_uuid,"
        "product_code"
    )

    callback = request.build_absolute_uri(
        "/billing/callback/esewa/"
    )

    signature_message = (
        f"total_amount={total_str},"
        f"transaction_uuid={transaction_uuid},"
        f"product_code={product_code}"
    )

    fields = {
        "amount": total_str,
        "tax_amount": "0",
        "total_amount": total_str,
        "transaction_uuid": transaction_uuid,
        "product_code": product_code,
        "product_service_charge": "0",
        "product_delivery_charge": "0",
        "success_url": callback,
        "failure_url": callback,
        "signed_field_names": signed_field_names,
        "signature": _esewa_signature(
            signature_message
        ),
    }

    return GatewayResult(
        Provider.ESEWA,
        transaction_uuid,
        form_action=_esewa_base(),
        form_fields=fields,
        metadata={
            "billing_customer_id": str(customer.pk),
            "customer_email": customer.email,
            "customer_name": customer.name,
            "product_code": product_code,
            "total_amount": total_str,
        },
    )

def verify_esewa_response(
    data_b64: str,
) -> dict:

    if not data_b64:
        raise ValueError(
            "eSewa response data is required."
        )

    try:
        raw = base64.b64decode(
            data_b64,
            validate=True,
        )

        data = json.loads(
            raw.decode("utf-8")
        )

    except (
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(
            "Invalid eSewa response."
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "Invalid eSewa response format."
        )

    signed_names = data.get(
        "signed_field_names"
    )

    signature = data.get(
        "signature"
    )

    if not signed_names:
        raise ValueError(
            "eSewa response has no "
            "signed_field_names."
        )

    if not signature:
        raise ValueError(
            "eSewa response has no signature."
        )

    names = [
        name.strip()
        for name in str(
            signed_names
        ).split(",")
        if name.strip()
    ]

    values = []

    for name in names:

        if name not in data:
            raise ValueError(
                f"Missing signed field: {name}"
            )

        values.append(
            f"{name}={data[name]}"
        )

    expected = _esewa_signature(
        ",".join(values)
    )

    if not hmac.compare_digest(
        expected,
        str(signature),
    ):
        raise ValueError(
            "Invalid eSewa response signature."
        )

    return data


def esewa_status(
    transaction_uuid: str,
    total_amount: str,
) -> dict:

    if not transaction_uuid:
        raise ValueError(
            "eSewa transaction UUID is required."
        )

    if not total_amount:
        raise ValueError(
            "eSewa total amount is required."
        )

    query = urlencode(
        {
            "product_code": (
                _esewa_product_code()
            ),
            "total_amount": total_amount,
            "transaction_uuid": (
                transaction_uuid
            ),
        }
    )

    return _json_get(
        f"{_esewa_status_url()}?{query}"
    )


def validate_esewa_transaction(
    data: dict,
    *,
    transaction_uuid: str,
    expected_amount: int,
    product_code: str,
) -> None:
    """
    Validate callback values against our own checkout.
    """

    if str(
        data.get("transaction_uuid", "")
    ) != str(transaction_uuid):
        raise ValueError(
            "eSewa transaction UUID mismatch."
        )

    if str(
        data.get("product_code", "")
    ) != str(product_code):
        raise ValueError(
            "eSewa product code mismatch."
        )

    try:
        callback_amount = (
            Decimal(
                str(data["total_amount"])
            ) * Decimal("100")
        ).quantize(
            Decimal("1")
        )

    except (
        KeyError,
        InvalidOperation,
    ) as exc:
        raise ValueError(
            "Invalid eSewa callback amount."
        ) from exc

    if int(callback_amount) != int(
        expected_amount
    ):
        raise ValueError(
            "eSewa callback amount does not "
            "match the checkout price."
        )