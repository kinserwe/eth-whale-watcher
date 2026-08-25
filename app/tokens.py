from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Token:
    symbol: str
    address: str
    decimals: int

    def to_raw(self, amount: int) -> int:
        return amount * 10**self.decimals

    def from_raw(self, raw: int) -> Decimal:
        return Decimal(raw) / 10**self.decimals


USDT = Token("USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 6)
