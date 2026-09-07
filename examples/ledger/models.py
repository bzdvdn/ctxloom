from pydantic import BaseModel

# Inputs — one type per fact, not one `Input(name, value)` tagged union.
# The dependency each formula has is expressed as *which type it consumes*,
# not as an `if name == "..."` check inside a shared handler.


class Hours(BaseModel):
    value: float


class Rate(BaseModel):
    value: float


class TaxRate(BaseModel):
    value: float


class DiscountRate(BaseModel):
    value: float


# Derived values — each recomputes only when something it actually consumes changes.


class LaborCost(BaseModel):
    value: float


class Tax(BaseModel):
    value: float


class Discount(BaseModel):
    value: float


class Total(BaseModel):
    value: float
