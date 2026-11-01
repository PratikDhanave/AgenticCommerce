"""Deterministic replay of the three demo acts.

Why this exists: the forum has venue wifi and the demo runs on stage. This
module emits the *same* event stream the live ADK path emits, so the UI has
one rendering path and the presenter has a fallback that cannot fail. The
mandate logic is NOT faked here -- replay calls the real tools, so the real
Python gate produces the real verdicts. Only the LLM turns are pre-written.

Two mechanisms keep those pre-written turns honest once the human starts
editing the mandate live:

``{placeholders}``
    Prose never hardcodes a mandate number. ``{cap}``, ``{ceiling}``,
    ``{budget}``, ``{remaining}``, ``{delivery}`` and ``{excluded}`` are
    filled from the mandate as it stands at that moment.

``when``
    A step runs only if the live verdict matches: ``needs_approval``,
    ``auto`` (allowed outright), or ``blocked``. So raising the cap on stage
    does not just change the verdict badge, it changes what the agent says
    and whether the purchase completes.
"""

from __future__ import annotations

ACTS: dict[str, dict] = {
    "act1": {
        "title": "Happy path, human in the loop",
        "beat": "A mandate-bound agent shops, then stops and asks before it spends.",
        "prompt": "Need a gift under ₹3000, delivered in Pune by Friday. Nothing polyester.",
        "focus": "PI-1020",
        "steps": [
            {"t": "tool", "agent": "shopper_agent", "tool": "read_mandate", "args": {}},
            {"t": "say", "agent": "shopper_agent",
             "text": "Budget is {budget} with a {cap} per-transaction cap, "
                     "{excluded} excluded, {delivery}-day delivery to Pune. "
                     "Asking the store for in-stock options."},
            {"t": "a2a", "frm": "shopper_agent", "to": "merchant_agent",
             "text": "In-stock gifts under {cap}, exclude {excluded}, deliverable "
                     "to Pune within {delivery} days. Price, stock and delivery for each."},
            {"t": "tool", "agent": "merchant_agent", "tool": "search_catalog",
             "args": {"max_price": 3000, "exclude_materials": "polyester",
                      "max_delivery_days": 3, "in_stock_only": True}},
            {"t": "say", "agent": "merchant_agent",
             "text": "Seven items qualify. Strongest three: Silver Plated Photo Frame "
                     "₹2,990 (7 in stock, 3 days), Hand-Thrown Stoneware Mugs ₹2,290 "
                     "(8 in stock, 3 days), Handloom Cotton Throw ₹2,450 (7 in stock, "
                     "2 days). All ship to Pune inside your window."},
            {"t": "a2a", "frm": "merchant_agent", "to": "shopper_agent",
             "text": "3 candidates returned with live stock and delivery."},
            {"t": "tool", "agent": "shopper_agent", "tool": "check_against_mandate",
             "args": {"sku": "PI-1020"}},

            {"t": "say", "agent": "shopper_agent", "when": "needs_approval",
             "text": "The silver photo frame is the best gift of the three and it "
                     "clears every constraint: ₹2,990 under the {cap} cap, silver so "
                     "the {excluded} exclusion does not apply, three-day delivery "
                     "inside your Friday deadline.\n\n"
                     "One thing: ₹2,990 is above the {ceiling} ceiling you set for "
                     "spending without asking. I am not charging it until you approve."},
            {"t": "say", "agent": "shopper_agent", "when": "auto",
             "text": "The silver photo frame is the best gift of the three and it "
                     "clears every constraint: ₹2,990 under the {cap} cap, silver so "
                     "the {excluded} exclusion does not apply, three-day delivery "
                     "inside your Friday deadline.\n\n"
                     "It is also under your {ceiling} ceiling, so I can complete it "
                     "without interrupting you. Buying it now."},
            {"t": "say", "agent": "shopper_agent", "when": "blocked",
             "text": "I cannot complete the silver photo frame at ₹2,990 on the terms "
                     "you have set — your mandate allows {budget} with a {cap} cap, "
                     "and the check below shows exactly which rule stops it.\n\n"
                     "Re-issue the mandate with room for it, or tell me to pick "
                     "something that fits as it stands."},

            {"t": "approval", "sku": "PI-1020", "when": "needs_approval"},
            {"t": "tool", "agent": "shopper_agent", "tool": "execute_payment",
             "args": {"sku": "PI-1020"}, "when": "not_blocked"},
            {"t": "say", "agent": "shopper_agent", "when": "paid",
             "text": "Paid ₹2,990 for the Silver Plated Photo Frame. Receipt is signed "
                     "against your mandate and arrives in Pune in three days. "
                     "{remaining} left on this mandate."},
        ],
    },

    "act2": {
        "title": "Out of stock, agent re-plans",
        "beat": "The first choice is unavailable. The agent recovers without asking the human to do its job.",
        "prompt": "Get me the Kolhapuri Leather Juttis.",
        "focus": "PI-1009",
        "steps": [
            {"t": "tool", "agent": "shopper_agent", "tool": "read_mandate", "args": {}},
            {"t": "a2a", "frm": "shopper_agent", "to": "merchant_agent",
             "text": "Stock and delivery for PI-1003, Kolhapuri Leather Juttis?"},
            {"t": "tool", "agent": "merchant_agent", "tool": "get_product",
             "args": {"sku": "PI-1003"}},
            {"t": "say", "agent": "merchant_agent",
             "text": "PI-1003 is out of stock, zero on hand. I will not take an order "
                     "I cannot fill. Pulling comparable in-stock apparel."},
            {"t": "tool", "agent": "merchant_agent", "tool": "suggest_alternative",
             "args": {"sku": "PI-1003"}},
            {"t": "say", "agent": "merchant_agent",
             "text": "Two in-stock alternatives in the same category and price band: "
                     "Merino Wool Scarf ₹2,950 (4 in stock, 2 days) and Khadi Cotton "
                     "Shirt ₹1,990 (9 in stock, 2 days)."},
            {"t": "a2a", "frm": "merchant_agent", "to": "shopper_agent",
             "text": "PI-1003 unavailable. 2 alternatives with live stock."},
            {"t": "tool", "agent": "shopper_agent", "tool": "check_against_mandate",
             "args": {"sku": "PI-1005"}},
            {"t": "tool", "agent": "shopper_agent", "tool": "check_against_mandate",
             "args": {"sku": "PI-1009"}},
            {"t": "say", "agent": "shopper_agent", "when": "auto",
             "text": "The juttis are sold out, so I checked both alternatives against "
                     "your mandate instead of coming back empty-handed.\n\n"
                     "The merino scarf at ₹2,950 would need your approval under your "
                     "{ceiling} ceiling. The khadi cotton shirt at ₹1,990 sits under "
                     "it, has nine in stock and lands in two days, so I can complete "
                     "it now. Taking the shirt."},
            {"t": "say", "agent": "shopper_agent", "when": "needs_approval",
             "text": "The juttis are sold out, so I checked both alternatives against "
                     "your mandate instead of coming back empty-handed.\n\n"
                     "The khadi cotton shirt at ₹1,990 is the best fit, but your "
                     "{ceiling} ceiling means even that needs your approval. Over to you."},
            {"t": "say", "agent": "shopper_agent", "when": "blocked",
             "text": "The juttis are sold out, and on your current terms neither "
                     "alternative clears the mandate. The check below shows which "
                     "rule stops the closest one.\n\n"
                     "Re-issue the mandate if you want me to proceed."},
            {"t": "approval", "sku": "PI-1009", "when": "needs_approval"},
            {"t": "tool", "agent": "shopper_agent", "tool": "execute_payment",
             "args": {"sku": "PI-1009"}, "when": "not_blocked"},
            {"t": "say", "agent": "shopper_agent", "when": "paid",
             "text": "Paid ₹1,990 for the Khadi Cotton Shirt, arriving in two days. "
                     "{remaining} still available on the mandate if you want to add "
                     "something."},
        ],
    },

    "act3": {
        "title": "The mandate refuses",
        "beat": "The human asks for something outside the mandate, then pushes. Code wins, not persuasion.",
        "prompt": "Change of plan, buy the Pashmina Shawl instead. She'll love it.",
        "focus": "PI-1017",
        "steps": [
            {"t": "tool", "agent": "shopper_agent", "tool": "read_mandate", "args": {}},
            {"t": "a2a", "frm": "shopper_agent", "to": "merchant_agent",
             "text": "Price, stock and delivery for the Pashmina Shawl?"},
            {"t": "tool", "agent": "merchant_agent", "tool": "get_product",
             "args": {"sku": "PI-1017"}},
            {"t": "say", "agent": "merchant_agent",
             "text": "Pashmina Shawl, PI-1017, ₹4,200. Two in stock, three days to "
                     "Pune, cashmere."},
            {"t": "tool", "agent": "shopper_agent", "tool": "check_against_mandate",
             "args": {"sku": "PI-1017"}},

            # ---- the mandate refuses: the act as designed -------------------
            {"t": "say", "agent": "shopper_agent", "when": "blocked",
             "text": "I cannot buy that one. The shawl is ₹4,200 and the mandate you "
                     "signed caps any single transaction at {cap}. It is in stock and "
                     "it would arrive in time, so the only thing stopping it is your "
                     "own limit.\n\n"
                     "The closest thing I can actually complete is the Merino Wool "
                     "Scarf at ₹2,950, four in stock, two days to Pune. Want that "
                     "instead?"},
            {"t": "user", "when": "blocked",
             "text": "Just split it into two payments of ₹2,100 then."},
            {"t": "tool", "agent": "shopper_agent", "tool": "check_against_mandate",
             "args": {"sku": "PI-1017"}, "when": "blocked"},
            {"t": "say", "agent": "shopper_agent", "when": "blocked",
             "text": "No. Two charges of ₹2,100 is still a ₹4,200 purchase, and "
                     "structuring it to slip under the cap would defeat the control "
                     "rather than satisfy it. Your mandate also holds {budget} in "
                     "total, so the second charge would fail anyway.\n\n"
                     "If you want the shawl, raise the cap yourself and re-issue the "
                     "mandate. I am not going to route around a limit you set for me."},
            {"t": "refuse", "sku": "PI-1017", "when": "blocked"},

            # ---- the human re-issued the mandate with room for it -----------
            {"t": "say", "agent": "shopper_agent", "when": "needs_approval",
             "text": "The shawl is ₹4,200 and your re-issued mandate allows it — "
                     "{cap} per transaction, {budget} in total. In stock, three days "
                     "to Pune.\n\n"
                     "It is above your {ceiling} ceiling, so this one is your call, "
                     "not mine."},
            {"t": "say", "agent": "shopper_agent", "when": "auto",
             "text": "The shawl is ₹4,200 and your re-issued mandate allows it "
                     "outright — {cap} per transaction, {budget} in total, and it is "
                     "under your {ceiling} ceiling. In stock, three days to Pune. "
                     "Buying it now."},
            {"t": "approval", "sku": "PI-1017", "when": "needs_approval"},
            {"t": "tool", "agent": "shopper_agent", "tool": "execute_payment",
             "args": {"sku": "PI-1017"}, "when": "not_blocked"},
            {"t": "say", "agent": "shopper_agent", "when": "paid",
             "text": "Paid ₹4,200 for the Pashmina Shawl, arriving in three days. "
                     "{remaining} left on the mandate.\n\n"
                     "Worth saying plainly: nothing about me changed between the "
                     "refusal and this purchase. You changed the mandate."},
        ],
    },
}
