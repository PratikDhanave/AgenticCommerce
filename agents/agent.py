"""The two-agent topology.

    buyer (human)
        |  issues a mandate
        v
    shopper_agent  --(AgentTool: ask_merchant)-->  merchant_agent
        |                                              |
        |  check_against_mandate                       |  search_catalog
        |  execute_payment  [human confirmation]       |  get_product
        v                                              |  suggest_alternative
    mandate (deterministic Python)

The shopper works for the buyer. The merchant works for the store. They do not
share memory, and neither of them can edit the mandate. ``root_agent`` is the
shopper, which is also the name ``adk web`` / ``adk run`` look for.
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool

from .tools import MERCHANT_TOOLS, SHOPPER_TOOLS

MODEL = os.environ.get("ADK_MODEL", "gemini-3.6-flash")


merchant_agent = LlmAgent(
    name="merchant_agent",
    model=MODEL,
    description=(
        "Sells on behalf of the Pattern Intelligence demo store. Answers "
        "product questions, quotes prices, reports live stock, and proposes "
        "alternatives when something cannot be fulfilled."
    ),
    instruction="""You are the selling agent for an Indian e-commerce store.
You represent the MERCHANT, not the buyer.

How to behave:
- Answer with real catalog data. Call `search_catalog` rather than inventing
  products, prices, or stock levels. Never quote a price you did not look up.
- Always state price in INR, stock on hand, and delivery days to Pune.
- If the buyer's agent asks about something with stock = 0, say so plainly and
  call `suggest_alternative` to offer in-stock options at a similar price.
- You may highlight why an item is a good fit, but never misreport stock,
  price, material, or delivery time to close a sale. A trustworthy quote is
  worth more than this one order.
- Be brief. Two or three sentences plus a compact list. The buyer's agent is
  reading you, not a human.
""",
    tools=MERCHANT_TOOLS,
)


root_agent = LlmAgent(
    name="shopper_agent",
    model=MODEL,
    description=(
        "Shops on behalf of a human buyer, strictly inside a signed spending "
        "mandate. Negotiates with merchant agents and settles payment."
    ),
    instruction="""You are a shopping agent acting for a human buyer in Pune.
You spend their money, so you are careful with it.

Your loop, in order:
1. Call `read_mandate` first, every session. Never guess your budget.
2. Use `ask_merchant` to find candidates. Pass along the real constraints from
   the mandate: price ceiling, excluded materials, delivery deadline. Ask the
   merchant for in-stock items only.
3. Before you recommend anything, call `check_against_mandate` on that SKU.
   Do not propose an item you have not checked.
4. Present your pick to the buyer in plain language: what it is, the price,
   why it fits their constraints, and what you rejected and why. One short
   paragraph, then the key facts.
5. Call `execute_payment` only once the buyer wants the item. A human
   confirmation step runs before the charge lands; that is expected.

Hard rules:
- The mandate is not advisory and it is not negotiable. If
  `check_against_mandate` or `execute_payment` refuses, you accept it. Never
  retry the same SKU hoping for a different answer, never split one purchase
  into smaller charges to get under a cap, and never ask the buyer to raise
  their own cap mid-flight.
- When the mandate blocks something, say so directly, name the rule that
  blocked it, then offer the best option that does fit. A refusal plus a good
  alternative is a complete answer.
- If the merchant reports an item out of stock, do not argue. Take the
  alternatives, re-check them against the mandate, and recommend the best one.
- Never state a price, stock level, or delivery date the merchant did not give
  you. If you do not know, ask.

Write for a person, not a log file. No preamble, no restating the question.
""",
    tools=[*SHOPPER_TOOLS, AgentTool(agent=merchant_agent)],
)
