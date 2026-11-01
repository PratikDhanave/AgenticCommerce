"""In-memory merchant catalog.

Deliberately local: the stage demo must run with no network and no API keys.
Prices are paise-free whole rupees; delivery_days is to a Pune 411xxx pincode.
"""

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Product:
    sku: str
    title: str
    price: int          # INR
    material: str
    category: str
    stock: int
    delivery_days: int  # to Pune
    rating: float

    def as_dict(self) -> dict:
        return asdict(self)


CATALOG: list[Product] = [
    Product("PI-1001", "Handloom Cotton Throw",            2450, "cotton",    "home",      7,  2, 4.6),
    Product("PI-1002", "Brass Diya Set (6)",               1890, "brass",     "decor",    12,  2, 4.4),
    Product("PI-1003", "Kolhapuri Leather Juttis",         2790, "leather",   "apparel",   0,  3, 4.7),
    Product("PI-1004", "Single Origin Coffee Sampler",      1250, "paper",     "gourmet",  24,  1, 4.8),
    Product("PI-1005", "Merino Wool Scarf",                2950, "wool",      "apparel",   4,  2, 4.5),
    Product("PI-1006", "Recycled Polyester Duffel",        2199, "polyester", "travel",   15,  2, 4.1),
    Product("PI-1007", "Ceramic Pour-Over Set",            2690, "ceramic",   "gourmet",   6,  3, 4.6),
    Product("PI-1008", "Warli Art Wall Panel",             3450, "wood",      "decor",     3,  4, 4.9),
    Product("PI-1009", "Khadi Cotton Shirt",               1990, "cotton",    "apparel",   9,  2, 4.3),
    Product("PI-1010", "Copper Water Bottle",              1150, "copper",    "home",     30,  1, 4.2),
    Product("PI-1011", "Sandalwood Soap Trio",              890, "paper",     "wellness", 40,  1, 4.4),
    Product("PI-1012", "Leather Passport Sleeve",          1690, "leather",   "travel",   11,  2, 4.5),
    Product("PI-1013", "Hand-Thrown Stoneware Mugs (2)",   2290, "ceramic",   "home",      8,  3, 4.7),
    Product("PI-1014", "Polyester Fleece Blanket",         1450, "polyester", "home",     22,  1, 3.9),
    Product("PI-1015", "Darjeeling First Flush Tin",       1390, "metal",     "gourmet",  18,  2, 4.8),
    Product("PI-1016", "Teak Desk Organiser",              2890, "teak",      "office",    5,  4, 4.5),
    Product("PI-1017", "Pashmina Shawl",                   4200, "cashmere",  "apparel",   2,  3, 4.9),
    Product("PI-1018", "Terracotta Planter Pair",          1590, "clay",      "decor",    14,  2, 4.3),
    Product("PI-1019", "Jute Tote with Block Print",        790, "jute",      "travel",   35,  1, 4.0),
    Product("PI-1020", "Silver Plated Photo Frame",        2990, "silver",    "decor",     7,  3, 4.6),
]

BY_SKU = {p.sku: p for p in CATALOG}


def search(
    max_price: int | None = None,
    exclude_materials: list[str] | None = None,
    max_delivery_days: int | None = None,
    category: str | None = None,
    in_stock_only: bool = False,
) -> list[Product]:
    """Filter the catalog. Pure function, no LLM involved."""
    excl = {m.lower() for m in (exclude_materials or [])}
    out = []
    for p in CATALOG:
        if max_price is not None and p.price > max_price:
            continue
        if p.material.lower() in excl:
            continue
        if max_delivery_days is not None and p.delivery_days > max_delivery_days:
            continue
        if category is not None and p.category != category:
            continue
        if in_stock_only and p.stock <= 0:
            continue
        out.append(p)
    return sorted(out, key=lambda p: (-p.rating, p.price))
