"""Tools exposed to the two ADK agents.

Two things worth noticing:

1. ``execute_payment`` re-runs the mandate check itself. The shopper agent is
   *also* told to preflight with ``check_against_mandate``, but the gate that
   actually matters is here, at the tool boundary. An agent that skips the
   preflight, or decides the cap is negotiable, still cannot spend the money.

2. ``execute_payment`` is wrapped with ``require_confirmation=True``, so ADK
   suspends the run and asks a human before the charge lands.
"""

from __future__ import annotations

from google.adk.tools import FunctionTool

from . import catalog, trace
from .mandate import Mandate, OK, NEEDS_HUMAN_APPROVAL

# One mandate per demo session, plus the terms the human last authored.
# The template is what gets re-issued at the start of every act, which is how
# editing the mandate actually changes what the agent is able to do.
_MANDATES: dict[str, Mandate] = {}
_TEMPLATES: dict[str, dict] = {}

EDITABLE = (
    "total_budget", "per_txn_cap", "auto_approve_below",
    "max_delivery_days", "excluded_materials",
)


def template_for(session_id: str) -> dict:
    if session_id not in _TEMPLATES:
        d = Mandate()
        _TEMPLATES[session_id] = {k: getattr(d, k) for k in EDITABLE}
    return _TEMPLATES[session_id]


def set_template(session_id: str, terms: dict) -> dict:
    t = dict(template_for(session_id))
    t.update({k: v for k, v in terms.items() if k in EDITABLE})
    _TEMPLATES[session_id] = t
    return t


def mandate_for(session_id: str) -> Mandate:
    if session_id not in _MANDATES:
        _MANDATES[session_id] = Mandate(**template_for(session_id))
    return _MANDATES[session_id]


def current_mandate() -> Mandate:
    return mandate_for(trace.current_session.get())


def reset_mandate(session_id: str) -> Mandate:
    """Issue a fresh mandate on the human's current terms."""
    m = Mandate(**template_for(session_id))
    _MANDATES[session_id] = m
    return m


# --------------------------------------------------------------------------
# Shopper-side tools
# --------------------------------------------------------------------------

def read_mandate() -> dict:
    """Read the spending mandate the human issued to you.

    Always call this first. It tells you your budget, your per-transaction
    cap, which materials the buyer excluded, and how fast delivery must be.
    """
    m = current_mandate()
    m.log("shopper_agent", "read_mandate", f"budget ₹{m.remaining:,} remaining")
    trace.emit("mandate_read", mandate=m.as_dict())
    return m.as_dict()


def check_against_mandate(sku: str) -> dict:
    """Check whether buying one unit of `sku` is permitted by the mandate.

    Call this before proposing anything to the buyer. Returns the verdict and
    every individual check that was run, so you can explain your reasoning.

    Args:
        sku: The product SKU, e.g. "PI-1013".
    """
    m = current_mandate()
    p = catalog.BY_SKU.get(sku)
    if p is None:
        trace.emit("mandate_decision", sku=sku, allowed=False,
                   code="UNKNOWN_SKU", reason=f"No such SKU: {sku}", checks=[])
        return {"allowed": False, "code": "UNKNOWN_SKU",
                "reason": f"No such SKU: {sku}"}

    d = m.evaluate(p.price, p.title, p.material, p.delivery_days, p.stock)
    m.log("mandate", "evaluate", f"{sku} ₹{p.price:,} -> {d.code}", d.code)
    trace.emit(
        "mandate_decision",
        sku=sku, title=p.title, amount=p.price,
        allowed=d.allowed, code=d.code, reason=d.reason, checks=d.checks,
        mandate=m.as_dict(),
    )
    return {"sku": sku, "title": p.title, "amount": p.price, **d.as_dict()}


def execute_payment(sku: str) -> dict:
    """Pay for one unit of `sku` and return a signed receipt.

    The mandate is re-checked here regardless of any earlier preflight. If the
    mandate refuses, no money moves and you must tell the buyer why.

    Args:
        sku: The product SKU to purchase.
    """
    m = current_mandate()
    p = catalog.BY_SKU.get(sku)
    if p is None:
        return {"paid": False, "code": "UNKNOWN_SKU",
                "reason": f"No such SKU: {sku}"}

    d = m.evaluate(p.price, p.title, p.material, p.delivery_days, p.stock)

    # A human tapping "approve" satisfies the HITL check, nothing else.
    if not d.allowed and d.code != NEEDS_HUMAN_APPROVAL:
        m.log("mandate", "refuse_payment",
              f"{sku} ₹{p.price:,}: {d.reason}", d.code)
        trace.emit("payment_refused", sku=sku, title=p.title, amount=p.price,
                   code=d.code, reason=d.reason, checks=d.checks,
                   mandate=m.as_dict())
        return {"paid": False, "code": d.code, "reason": d.reason,
                "checks": d.checks}

    receipt = m.charge(p.price, p.sku, p.title)
    m.log("mandate", "charge",
          f"{sku} ₹{p.price:,}; ₹{m.remaining:,} left", OK)
    trace.emit("payment_settled", sku=sku, title=p.title, amount=p.price,
               receipt=receipt, verified=Mandate.verify(receipt),
               mandate=m.as_dict())
    return {"paid": True, "code": OK, "receipt": receipt,
            "signature_valid": Mandate.verify(receipt),
            "remaining_budget": m.remaining}


# --------------------------------------------------------------------------
# Merchant-side tools
# --------------------------------------------------------------------------

def search_catalog(
    max_price: int = 0,
    exclude_materials: str = "",
    max_delivery_days: int = 0,
    in_stock_only: bool = False,
) -> dict:
    """Search the merchant's live catalog.

    Args:
        max_price: Maximum unit price in INR. 0 means no limit.
        exclude_materials: Comma-separated materials to exclude, e.g. "polyester".
        max_delivery_days: Maximum delivery days to Pune. 0 means no limit.
        in_stock_only: If true, omit items with zero stock.
    """
    excl = [s.strip() for s in exclude_materials.split(",") if s.strip()]
    results = catalog.search(
        max_price=max_price or None,
        exclude_materials=excl or None,
        max_delivery_days=max_delivery_days or None,
        in_stock_only=in_stock_only,
    )
    items = [p.as_dict() for p in results[:8]]
    trace.emit("catalog_search",
               query={"max_price": max_price, "exclude_materials": excl,
                      "max_delivery_days": max_delivery_days,
                      "in_stock_only": in_stock_only},
               count=len(items), items=items)
    return {"count": len(items), "items": items}


def get_product(sku: str) -> dict:
    """Fetch full detail, including live stock, for one SKU.

    Args:
        sku: The product SKU.
    """
    p = catalog.BY_SKU.get(sku)
    if p is None:
        return {"found": False, "sku": sku}
    trace.emit("product_lookup", sku=sku, item=p.as_dict())
    return {"found": True, **p.as_dict()}


def suggest_alternative(sku: str) -> dict:
    """Suggest in-stock alternatives when a SKU cannot be fulfilled.

    Args:
        sku: The SKU that could not be fulfilled.
    """
    p = catalog.BY_SKU.get(sku)
    if p is None:
        return {"alternatives": []}
    alts = [
        q.as_dict() for q in catalog.CATALOG
        if q.sku != sku and q.stock > 0
        and q.category == p.category
        and abs(q.price - p.price) <= 900
    ][:3]
    if not alts:
        alts = [
            q.as_dict() for q in catalog.search(
                max_price=p.price + 400, in_stock_only=True,
                max_delivery_days=p.delivery_days,
            )
        ][:3]
    trace.emit("alternatives_offered", for_sku=sku,
               reason=f"{p.title} has stock={p.stock}", alternatives=alts)
    return {"for_sku": sku, "unavailable_reason": f"stock={p.stock}",
            "alternatives": alts}


SHOPPER_TOOLS = [
    FunctionTool(read_mandate),
    FunctionTool(check_against_mandate),
    FunctionTool(execute_payment, require_confirmation=True),
]

MERCHANT_TOOLS = [
    FunctionTool(search_catalog),
    FunctionTool(get_product),
    FunctionTool(suggest_alternative),
]
