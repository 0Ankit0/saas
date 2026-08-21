from django.conf import settings
from hashids import Hashids


hashids = Hashids(
    salt=settings.HASHID_SALT,
    min_length=8,
)


def encode_hashid(value: int) -> str:
    return hashids.encode(value)


def decode_hashid(value: str) -> int:
    decoded = hashids.decode(value)

    if not decoded:
        raise ValueError("Invalid HashID.")

    return decoded[0]