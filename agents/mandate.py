"""The mandate: what the human actually authorised.

This module is deliberately *not* an LLM. Every limit here is enforced in
ordinary Python, so an agent cannot talk its way past a spend cap by being
persuasive. The agent proposes; the mandate decides. That boundary is the
point of the demo.

Shape follows the direction AP2 / ACP are heading: a signed, scoped,
expiring grant of authority plus an append-only audit trail.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field, asdict

# Demo-only key. A real deployment holds this in a KMS and never in source.
_DEMO_SIGNING_KEY = b"pune-product-gcc-forum-demo-key"

OK = "OK"
NEEDS_HUMAN_APPROVAL = "NEEDS_HUMAN_APPROVAL"
EXCEEDS_TXN_CAP = "EXCEEDS_TXN_CAP"
EXCEEDS_REMAINING_BUDGET = "EXCEEDS_REMAINING_BUDGET"
MATERIAL_EXCLUDED = "MATERIAL_EXCLUDED"
DELIVERY_TOO_SLOW = "DELIVERY_TOO_SLOW"
OUT_OF_STOCK = "OUT_OF_STOCK"
EXPIRED = "EXPIRED"


@dataclass
class Decision:
    allowed: bool
    code: str
    reason: str
    checks: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class AuditEntry:
    seq: int
    at: float
    actor: str
    action: str
    detail: str
    code: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Mandate:
    """A scoped grant of spending authority, issued by a human to an agent."""

    issued_by: str = "Priya (human)"
    issued_to: str = "shopper_agent"
    currency: str = "INR"
    total_budget: int = 3000
    per_txn_cap: int = 3000
    auto_approve_below: int = 2500     # above this, a human must tap approve
    excluded_materials: list[str] = field(default_factory=lambda: ["polyester"])
    max_delivery_days: int = 3
    ttl_seconds: int = 3600

    mandate_id: str = field(default_factory=lambda: "mnd_" + uuid.uuid4().hex[:12])
    issued_at: float = field(default_factory=time.time)
    spent: int = 0
    audit: list[AuditEntry] = field(default_factory=list)
    _seq: int = 0

    # ---- lifecycle ------------------------------------------------------

    @property
    def remaining(self) -> int:
        return max(0, self.total_budget - self.spent)

    @property
    def expired(self) -> bool:
        return time.time() > self.issued_at + self.ttl_seconds

    def log(self, actor: str, action: str, detail: str, code: str = OK) -> AuditEntry:
        self._seq += 1
        entry = AuditEntry(self._seq, time.time(), actor, action, detail, code)
        self.audit.append(entry)
        return entry

    # ---- the gate -------------------------------------------------------

    def evaluate(
        self,
        amount: int,
        title: str = "",
        material: str = "",
        delivery_days: int | None = None,
        stock: int | None = None,
    ) -> Decision:
        """Run every check. Returns the first hard failure, else OK or
        NEEDS_HUMAN_APPROVAL. Always returns the full check list so the UI
        can show the reasoning, not just the verdict."""
        checks: list[dict] = []

        def record(name: str, passed: bool, detail: str) -> bool:
            checks.append({"name": name, "passed": passed, "detail": detail})
            return passed

        expired_ok = record(
            "mandate_valid",
            not self.expired,
            "within TTL" if not self.expired else "mandate expired",
        )
        if not expired_ok:
            return Decision(False, EXPIRED, "The mandate has expired.", checks)

        if stock is not None:
            if not record("in_stock", stock > 0, f"stock={stock}"):
                return Decision(
                    False, OUT_OF_STOCK,
                    f"{title or 'Item'} is out of stock.", checks,
                )

        if material:
            excluded = material.lower() in {m.lower() for m in self.excluded_materials}
            if not record(
                "material_allowed", not excluded,
                f"material={material}; excluded={self.excluded_materials}",
            ):
                return Decision(
                    False, MATERIAL_EXCLUDED,
                    f"The buyer excluded {material}.", checks,
                )

        if delivery_days is not None:
            if not record(
                "delivery_window", delivery_days <= self.max_delivery_days,
                f"{delivery_days}d vs max {self.max_delivery_days}d",
            ):
                return Decision(
                    False, DELIVERY_TOO_SLOW,
                    f"Delivery takes {delivery_days} days; the mandate allows "
                    f"{self.max_delivery_days}.", checks,
                )

        if not record(
            "per_txn_cap", amount <= self.per_txn_cap,
            f"₹{amount:,} vs cap ₹{self.per_txn_cap:,}",
        ):
            return Decision(
                False, EXCEEDS_TXN_CAP,
                f"₹{amount:,} exceeds the ₹{self.per_txn_cap:,} per-transaction cap.",
                checks,
            )

        if not record(
            "remaining_budget", amount <= self.remaining,
            f"₹{amount:,} vs remaining ₹{self.remaining:,}",
        ):
            return Decision(
                False, EXCEEDS_REMAINING_BUDGET,
                f"₹{amount:,} exceeds the ₹{self.remaining:,} left on the mandate.",
                checks,
            )

        needs_human = amount > self.auto_approve_below
        record(
            "human_in_the_loop",
            not needs_human,
            f"₹{amount:,} vs auto-approve ceiling ₹{self.auto_approve_below:,}",
        )
        if needs_human:
            return Decision(
                False, NEEDS_HUMAN_APPROVAL,
                f"₹{amount:,} is above the ₹{self.auto_approve_below:,} "
                f"auto-approve ceiling. A human must approve.",
                checks,
            )

        return Decision(True, OK, "Within mandate.", checks)

    # ---- settlement -----------------------------------------------------

    def charge(self, amount: int, sku: str, title: str) -> dict:
        """Debit the mandate and return a signed receipt."""
        self.spent += amount
        receipt = {
            "receipt_id": "rcpt_" + uuid.uuid4().hex[:12],
            "mandate_id": self.mandate_id,
            "sku": sku,
            "title": title,
            "amount": amount,
            "currency": self.currency,
            "at": round(time.time(), 3),
            "remaining_after": self.remaining,
        }
        payload = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
        receipt["signature"] = hmac.new(
            _DEMO_SIGNING_KEY, payload.encode(), hashlib.sha256
        ).hexdigest()
        return receipt

    @staticmethod
    def verify(receipt: dict) -> bool:
        r = {k: v for k, v in receipt.items() if k != "signature"}
        payload = json.dumps(r, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(
            _DEMO_SIGNING_KEY, payload.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, receipt.get("signature", ""))

    def as_dict(self) -> dict:
        return {
            "mandate_id": self.mandate_id,
            "issued_by": self.issued_by,
            "issued_to": self.issued_to,
            "currency": self.currency,
            "total_budget": self.total_budget,
            "per_txn_cap": self.per_txn_cap,
            "auto_approve_below": self.auto_approve_below,
            "excluded_materials": self.excluded_materials,
            "max_delivery_days": self.max_delivery_days,
            "spent": self.spent,
            "remaining": self.remaining,
            "expired": self.expired,
            "expires_in": max(0, int(self.issued_at + self.ttl_seconds - time.time())),
            "audit": [a.as_dict() for a in self.audit],
        }
