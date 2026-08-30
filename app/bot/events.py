from app.models import AddressCategory

EVENT_MAP: dict[tuple[AddressCategory | None, AddressCategory | None], str] = {
    (AddressCategory.TREASURY, AddressCategory.EXCHANGE): "New supply",
    (AddressCategory.TREASURY, None): "New supply",
    (AddressCategory.EXCHANGE, AddressCategory.TREASURY): "Redemption",
    (None, AddressCategory.TREASURY): "Redemption",
    (None, AddressCategory.EXCHANGE): "Exchange inflow",
    (AddressCategory.EXCHANGE, None): "Exchange outflow",
    (AddressCategory.EXCHANGE, AddressCategory.EXCHANGE): "Inter-exchange transfer",
    (None, AddressCategory.BRIDGE): "Bridge inflow",
    (AddressCategory.BRIDGE, None): "Bridge outflow",
    (None, AddressCategory.DEFI): "Protocol inflow",
    (AddressCategory.DEFI, None): "Protocol outflow",
    (None, None): "",
    (AddressCategory.EXCHANGE, AddressCategory.MARKET_MAKER): "",
    (AddressCategory.MARKET_MAKER, AddressCategory.EXCHANGE): "",
}
