from rest_framework import serializers

from .utils import decode_hashid, encode_hashid


class HashIDField(serializers.Field):
    """
    A custom serializer field for encoding and decoding HashIDs.
    """
    def __init__(self, **kwargs):
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)
        
    def to_representation(self, value: int) -> str:
        return encode_hashid(value)

    def to_internal_value(self, data: object) -> int:
        if not isinstance(data, str):
            raise serializers.ValidationError(
                "HashID must be a string."
            )

        try:
            return decode_hashid(data)
        except ValueError:
            raise serializers.ValidationError(
                "Invalid HashID."
            )