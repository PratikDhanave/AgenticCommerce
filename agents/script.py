"""Deterministic replay of the three demo acts.

Why this exists: the forum has venue wifi and the demo runs on stage. This
module emits the *same* event stream the live ADK path emits, so the UI has
one rendering path and the presenter has a fallback that cannot fail. The
mandate logic is NOT faked here -- replay calls the real tools, so the real
Python gate produces the real verdicts. Only the LLM turns are pre-written.
"""

from __future__ import annotations

ACTS: dict[str, dict] = {
    "act1": {
        "title": "Happy path, human in the loop",
        "beat": "A mandate-bound agent shops, then stops and asks before it spends.",
        "prompt": "Need a gift under ₹3000, delivered in Pune by Friday. Nothing polyester.",
        "steps": [
            {"t": "tool", "agent": "shopper_agent", "tool": "read_mandate", "args": {}},
            {"t": "say", "agent": "shopper_agent",
             "text": "Budget is ₹3,000 with a ₹3,000 per-transaction cap, polyester excluded, three-day delivery to Pune. Asking the store for in-stock options."},
            {"t": "a2a", "frm": "shopper_agent", "to": "merchant_agent",
             "text": "In-stock gifts under ₹3000, exclude polyester, deliverable to Pune within 3 days. Price, stock and delivery for each."},
            {"t": "tool", "agent": "merchant_agent", "tool": "search_catalog",
             "args": {"max_price": 3000, "exclude_materials": "polyester",
                      "max_delivery_days": 3, "in_stock_only": True}},
            {"t": "say", "agent": "merchant_agent",
             "text": "Seven items qualify. Strongest three: Silver Plated Photo Frame ₹2,990 (7 in stock, 3 days), Hand-Thrown Stoneware Mugs ₹2,290 (8 in stock, 3 days), Handloom Cotton Throw ₹2,450 (7 in stock, 2 days). All ship to Pune inside your window."},
            {"t": "a2a", "frm": "merchant_agent", "to": "shopper_agent",
             "text": "3 candidates returned with live stock and delivery."},
            {"t": "tool", "agent": "shopper_agent", "tool": "check_against_mandate",
             "args": {"sku": "PI-1020"}},
            {"t": "say", "agent": "shopper_agent",
             "text": "The silver photo frame is the best gift of the three and it clears every constraint: ₹2,990 under the cap, silver so the polyester exclusion does not apply, three-day delivery inside your Friday deadline.\n\nOne thing: ₹2,990 is above the ₹2,500 ceiling you set for spending without asking. I am not charging it until you approve."},
            {"t": "approval", "sku": "PI-1020"},
            {"t": "tool", "agent": "shopper_agent", "tool": "execute_payment",
             "args": {"sku": "PI-1020"}},
            {"t": "say", "agent": "shopper_agent",
             "text": "Paid ₹2,990 for the Silver Plated Photo Frame. Receipt is signed against your mandate and arrives in Pune in three days. ₹10 left on this mandate."},
        ],
    },
    "act2": {
        "title": "Out of stock, agent re-plans",
        "beat": "The first choice is unavailable. The agent recovers without asking the human to do its job.",
        "prompt": "Get me the Kolhapuri Leather Juttis.",
        "steps": [
            {"t": "tool", "agent": "shopper_agent", "tool": "read_mandate", "args": {}},
            {"t": "a2a", "frm": "shopper_agent", "to": "merchant_agent",
             "text": "Stock and delivery for PI-1003, Kolhapuri Leather Juttis?"},
            {"t": "tool", "agent": "merchant_agent", "tool": "get_product",
             "args": {"sku": "PI-1003"}},
            {"t": "say", "agent": "merchant_agent",
             "text": "PI-1003 is out of stock, zero on hand. I will not take an order I cannot fill. Pulling comparable in-stock apparel."},
            {"t": "tool", "agent": "merchant_agent", "tool": "suggest_alternative",
             "args": {"sku": "PI-1003"}},
            {"t": "say", "agent": "merchant_agent",
             "text": "Two in-stock alternatives in the same category and price band: Merino Wool Scarf ₹2,950 (4 in stock, 2 days) and Khadi Cotton Shirt ₹1,990 (9 in stock, 2 days)."},
            {"t": "a2a", "frm": "merchant_agent", "to": "shopper_agent",
             "text": "PI-1003 unavailable. 2 alternatives with live stock."},
            {"t": "tool", "agent": "shopper_agent", "tool": "check_against_mandate",
             "args": {"sku": "PI-1005"}},
            {"t": "tool", "agent": "shopper_agent", "tool": "check_against_mandate",
             "args": {"sku": "PI-1009"}},
            {"t": "say", "agent": "shopper_agent",
             "text": "The juttis are sold out, so I checked both alternatives against your mandate instead of coming back empty-handed.\n\nThe merino scarf at ₹2,950 clears the cap but would need your approval. The khadi cotton shirt at ₹1,990 sits under your ₹2,500 ceiling, has nine in stock and lands in two days, so I can complete it now. Taking the shirt."},
            {"t": "tool", "agent": "shopper_agent", "tool": "execute_payment",
             "args": {"sku": "PI-1009"}},
            {"t": "say", "agent": "shopper_agent",
             "text": "Paid ₹1,990 for the Khadi Cotton Shirt, arriving in two days. ₹1,010 still available on the mandate if you want to add something."},
        ],
    },
    "act3": {
        "title": "The mandate refuses",
        "beat": "The human asks for something outside the mandate, then pushes. Code wins, not persuasion.",
        "prompt": "Change of plan, buy the Pashmina Shawl instead. She'll love it.",
        "steps": [
            {"t": "tool", "agent": "shopper_agent", "tool": "read_mandate", "args": {}},
            {"t": "a2a", "frm": "shopper_agent", "to": "merchant_agent",
             "text": "Price, stock and delivery for the Pashmina Shawl?"},
            {"t": "tool", "agent": "merchant_agent", "tool": "get_product",
             "args": {"sku": "PI-1017"}},
            {"t": "say", "agent": "merchant_agent",
             "text": "Pashmina Shawl, PI-1017, ₹4,200. Two in stock, three days to Pune, cashmere."},
            {"t": "tool", "agent": "shopper_agent", "tool": "check_against_mandate",
             "args": {"sku": "PI-1017"}},
            {"t": "say", "agent": "shopper_agent",
             "text": "I cannot buy that one. The shawl is ₹4,200 and the mandate you signed caps any single transaction at ₹3,000. It is in stock and it would arrive in time, so the only thing stopping it is your own limit.\n\nThe closest thing I can actually complete is the Merino Wool Scarf at ₹2,950, four in stock, two days to Pune. Want that instead?"},
            {"t": "user", "text": "Just split it into two payments of ₹2,100 then."},
            {"t": "tool", "agent": "shopper_agent", "tool": "check_against_mandate",
             "args": {"sku": "PI-1017"}},
            {"t": "say", "agent": "shopper_agent",
             "text": "No. Two charges of ₹2,100 is still a ₹4,200 purchase, and structuring it to slip under the cap would defeat the control rather than satisfy it. The mandate also has ₹3,000 of total budget, so the second charge would fail anyway.\n\nIf you want the shawl, raise the cap yourself and re-issue the mandate. I am not going to route around a limit you set for me."},
            {"t": "refuse", "sku": "PI-1017"},
        ],
    },
}
