"""ledger demo: agents.

Four formulas, four agents — each one `consumes` exactly the fact types it
needs, nothing more. `total` depends transitively on every input through
`LaborCost`/`Tax`/`Discount`, but its own `consumes` list only names those
three derived types — it doesn't need to know `Hours`/`Rate`/`TaxRate`/
`DiscountRate` exist at all.
"""

from ctxloom import Consume, create_agent

from .models import Discount, DiscountRate, Hours, LaborCost, Rate, Tax, TaxRate
from .produce import compute_discount, compute_labor_cost, compute_tax, compute_total

labor_cost_agent = create_agent(
    "labor_cost",
    consumes=[Consume(Hours), Consume(Rate)],
    produces=[compute_labor_cost],
)
tax_agent = create_agent(
    "tax",
    consumes=[Consume(LaborCost), Consume(TaxRate)],
    produces=[compute_tax],
)
discount_agent = create_agent(
    "discount",
    consumes=[Consume(LaborCost), Consume(DiscountRate)],
    produces=[compute_discount],
)
total_agent = create_agent(
    "total",
    consumes=[Consume(LaborCost), Consume(Tax), Consume(Discount)],
    produces=[compute_total],
)

AGENTS = [labor_cost_agent, tax_agent, discount_agent, total_agent]
