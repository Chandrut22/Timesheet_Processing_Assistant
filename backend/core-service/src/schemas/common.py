from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

# Decimal in Python and the DB (exact), but a plain number in JSON
# (Pydantic would otherwise send "8.00" as a string).
HoursOut = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
# Money: same idea. Stored and calculated as exact Decimal; sent as a number (2 decimals).
MoneyOut = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int
