"""We used AI to help build our frontend model.
Break-even model: This calculates the order volume at which it is feasible to ship directly 
from South Africa (SA) vs building a regional warehouse

We assume warehousing costs are in USD or Pounds and shipping costs are in ZAR

We consider each unit to be a game 

Direct shpping:
    Unit cost (ZAR)
    Total cost (ZAR)

Warehouse costs:
    Variable costs (US/UK)
    Fixed costs (US/UK)
    Holding costs (US/UK)
    Total regional costs =  Variable costs (US/UK) + Fixed costs (US/UK) + Holding costs (US/UK)


Break even point (a): Total costs (direct) = Total cost (Warehouse)
Break even volume: Q* (only if warehouse is cheaper at some volume, otherwise None)
q = monthly order volume (units/month)

Assumptions:
Break even point
 Constant units costs (no frieght tiers). 
Steady demand woth normally distributed variation (CV.
One warehouse per region.
Each inbound shipment is the EOQ sized order.
Fixed costs remain constant for our time period.

"""


from dataclasses import dataclass, field, fields, replace
from math import sqrt
from typing import Dict, List, Optional


class ModelError(ValueError):
    """Raised when inputs are invalid."""
#When an icorrect input is given, this error is raised to the user to indicate that the input is invalid and needs to be corrected.

def _f(label, unit, group, default):
    return field(default=default, metadata={"label": label, "unit": unit, "group": group})
#Each input field is defined with a label, unit, group, and default value. 
#It avoids repetition and makes it easier to manage the input fields in the RegionInputs dataclass.

G_D = "Direct shipping from SA"
G_V = "Warehouse: per-unit costs"
G_I = "Inventory and replenishment"
G_F = "Warehouse: fixed costs"

#This code defines the groups for the input fields, which are used to categorize the inputs in the RegionInputs dataclass.
#the groups are used to organize the inputs and make it easier to understand the different types of costs involved in the break-even analysis.
@dataclass(frozen=True) # Frozen = true means that once you set a value in the what-if analysis , it will keep that value the same until you change the value again

class RegionInputs: #Contains all the inputs for one region at a time. US or UK
    fx_zar_per_usd: float = _f("Exchange rate", "ZAR per USD", G_D, 18.0)
    direct_freight_usd: float = _f("Freight per unit", "USD", G_D, 14.00)
    direct_customs_ins_usd: float = _f("Customs, duties and insurance per unit", "USD", G_D, 2.50)
    sa_handling_zar: float = _f("SA pick, pack and handling per unit", "ZAR", G_D, 20.0)
    inbound_freight_usd: float = _f("Bulk inbound freight per unit", "USD", G_V, 2.80)
    inbound_customs_ins_usd: float = _f("Inbound customs, duties and insurance per unit", "USD", G_V, 2.50)
    #pick_pack_usd: float = _f("Pick and pack per unit", "USD", G_V, 1.80)
    #local_delivery_usd: float = _f("Local delivery per unit", "USD", G_V, 4.50)
    unit_cost_zar: float = _f("Product cost per unit (values inventory)", "ZAR", G_I, 144.0)
    holding_rate_annual: float = _f("Annual holding rate (fraction of value)", "0-1", G_I, 0.20)
    lead_time_months: float = _f("Replenishment lead time (L)", "months", G_I, 1.5)
    demand_cv: float = _f("Demand variability (CV)", "ratio", G_I, 0.30)
    service_z: float = _f("Service level factor (z)", "z-score", G_I, 1.65)
    rent_usd_month: float = _f("Warehouse lease", "USD/month", G_F, 2500.0)
    staff_usd_month: float = _f("Warehouse staff", "USD/month", G_F, 3000.0)
    admin_usd_month: float = _f("Software, insurance and admin", "USD/month", G_F, 400.0)
    setup_usd: float = _f("One-off setup cost", "USD", G_F, 15000.0)
    amortisation_months: float = _f("Setup amortisation period", "months", G_F, 36.0)
    inbound_shipment_fixed_usd: float = _f("Fixed cost per inbound shipment (S)", "USD", G_I, 600.0)
#Assigning a default value to each input using the _f function.
    
    def __post_init__(self):
        for f in fields(self):
            v = getattr(self, f.name)
            if not isinstance(v, (int, float)) or v < 0:
                raise ModelError(f"{f.metadata['label']} must be a number of 0 or more.")
        for name in ("fx_zar_per_usd", "amortisation_months"):
            if getattr(self, name) <= 0:
                raise ModelError(f"{self.__dataclass_fields__[name].metadata['label']} must be above 0.")
#Self refers to each instance in the class RegionInputs
# The function post_init checks each self, if it is either not a number or below zero. If it is either it will return an error message.
 
#The p is an alias for the RegionInputs class, which is used to pass the input values to the functions.

def unit_value_usd(p: RegionInputs):
    return p.unit_cost_zar / p.fx_zar_per_usd
# This function is converting the unit cost from ZAR to USD.

def direct_variable_cost(p: RegionInputs):
    """v_d (USD/unit)."""
    return p.direct_freight_usd + p.direct_customs_ins_usd + p.sa_handling_zar / p.fx_zar_per_usd
#This function calculates the shipping cost per unit for direct shipping from South Africa to the region. 

def annual_holding_cost_per_unit(p: RegionInputs):
    """H (USD per unit per year)."""
    return p.holding_rate_annual * unit_value_usd(p)


def safety_holding_cost_per_unit(p: RegionInputs):
    """Monthly carrying cost of safety stock per unit of monthly volume."""
    return annual_holding_cost_per_unit(p) / 12 * p.service_z * p.demand_cv * sqrt(p.lead_time_months)
#The Annual holding rate is used to calculate the cost of carrying the cost

def cycle_cost_coefficient(p: RegionInputs):
    """k in (monthly EOQ ordering + cycle-stock cost) = k * sqrt(Q)."""
    return sqrt(p.inbound_shipment_fixed_usd * annual_holding_cost_per_unit(p) / 6)
#this function calculates the cycle cost coefficient, which is used to determine the total cost of using a warehouse. 
# It takes into account the fixed cost per inbound shipment and the annual holding cost per unit.


def warehouse_variable_cost(p: RegionInputs):
    """v_w (USD/unit)."""
    return (p.inbound_freight_usd + p.inbound_customs_ins_usd  + safety_holding_cost_per_unit(p))
#the warehouse cost consists of: inbound freight, customs, safety stock

def warehouse_fixed_cost(p: RegionInputs):
    """F_w (USD/month)."""
    return (p.rent_usd_month + p.staff_usd_month + p.admin_usd_month
            + p.setup_usd / p.amortisation_months)
# the warehouse variable cost consists of: rent, staff salaries, admin, setup cost 
#Amortisation is spreading out a cost over a period of time, instead of once off.

def calculate_eoq(demand: float, order_cost: float, hold_cost: float):
    """EOQ = sqrt(2*D*S/H). demand per year, order_cost per order, hold_cost per unit per year."""
    if hold_cost <= 0:
        raise ModelError("Holding cost must be above 0 to calculate an EOQ.")
    if demand < 0 or order_cost < 0:
        raise ModelError("Demand and ordering cost must be 0 or more.")
    return sqrt(2 * demand * order_cost / hold_cost)
# If the warehouse is a feasible option - it will calculate the optimal order quantity (EOQ)
#The holding cost can never be negative or zero and demand can not be negative. This is why it should raise an error string instead of returning a vlaue(which is an error)

def orders_per_year(demand: float, order_qty: float):
    return 0.0 if order_qty == 0 else demand / order_qty
#The number of orders that are made per year based on the optimum policy is calculated using demand and EOQ??


def total_annual_cost(demand: float, order_cost: float, hold_cost: float, order_qty: float):
    """(D/Q)*S + (Q/2)*H."""
    return orders_per_year(demand, order_qty) * order_cost + order_qty / 2 * hold_cost
#This function returns the total annual cost of using a warehouse based on the demand, order cost, holding cost, and order quantity.

def reorder_point(p: RegionInputs, q: float):
    """Demand during lead time + safety stock (units)."""
    return q * p.lead_time_months + safety_stock(p, q)
#The amount that we need to reorder to satisfy damnd and replenish our safety stock.

def safety_stock(p: RegionInputs, q: float):
    return p.service_z * p.demand_cv * q * sqrt(p.lead_time_months)
#Calculates safety stock


def replenishment_plan(p: RegionInputs, q: float):
    """Warehouse restocking plan at monthly volume q."""
    _check_q(q) ## if q is less than 0, it returns an error to the user saying monthly order volume can not be negative
    d = 12 * q
    h = annual_holding_cost_per_unit(p)
    eoq = calculate_eoq(d, p.inbound_shipment_fixed_usd, h) if h > 0 else 0.0 ## if the holding cost is zero  we dont want it to return an error, instead we want it to return zero, to indicate the EOQ is zero, therefore no warehouse just direct shipping is the best option
    opy = orders_per_year(d, eoq) ## this calculates the number of orders per year based on the demand and EOQ
    return {"eoq": eoq, "orders_per_year": opy, 
            "days_between": 365 / opy if opy else 0.0, ##  This function calculates the number of days between shipments
            "safety_stock": safety_stock(p, q), 
              "reorder_point": reorder_point(p, q)}


def _check_q(q: float):
    if q < 0:
        raise ModelError("Monthly order volume must be 0 or more.")
    #Error warning: monthly volumes cannot be less then zero.
    

def total_cost_direct(p: RegionInputs, q: float):
    _check_q(q)
    return q * direct_variable_cost(p)


def total_cost_warehouse(p: RegionInputs, q: float):
    _check_q(q)
    return warehouse_fixed_cost(p) + q * warehouse_variable_cost(p) + cycle_cost_coefficient(p) * sqrt(q)


def break_even_volume(p: RegionInputs):
    """Q* in units/month, or None if the warehouse is not an option  (v_d <= v_w)."""
    ## This function calculates the break-even volume, which is the point at which the total cost of direct shipping equals the total cost of using a warehouse.
    ## If the variable cost of direct shipping is less than or equal to the variable cost of using a warehouse, it returns None, indicating that using a warehouse is not a feasible option.
    a = direct_variable_cost(p) - warehouse_variable_cost(p)
    if a <= 0: ##this means that the variable cost of direct shipping is less than or equal to the variable cost of using a warehouse, so it is not feasible to use a warehouse. Therefore, the function returns None.
        return None
    k = cycle_cost_coefficient(p) 
    f = warehouse_fixed_cost(p)
    x = (k + sqrt(k * k + 4 * a * f)) / (2 * a) 
    return x * x


def decision_threshold(p: RegionInputs):
    be = break_even_volume(p)
    return None if be is None else be 
#It shows the break-even thresh-hold

def recommend(p: RegionInputs, q: float) :
    be = break_even_volume(p)
    if be is None or q < be:
        return "Ship from SA" 
    else:
        return "Use warehouse" 
#This is telling the user what to do according to the break even point

def monthly_saving(p: RegionInputs, q: float):
    """Direct minus warehouse cost at Q (positive = warehouse cheaper)."""
    return total_cost_direct(p, q) - total_cost_warehouse(p, q)
#Calculates the monthly saving of using a warehouse instead of direct shipping. 

def cost_curve(p: RegionInputs, q_max: float, points: int = 25):
    step = q_max / (points - 1)
    return [{"q": round(i * step, 1), "direct": total_cost_direct(p, i * step),
             "warehouse": total_cost_warehouse(p, i * step)} for i in range(points)]
# This function generates a cost curve for both direct shipping and warehouse costs over a range of order volumes. ach point. 
# This allows for visualizing how costs change with varying order volumes.   

def apply_scenario(p: RegionInputs, freight_pct=0.0, customs_pct=0.0, lease_pct=0.0, fx_pct=0.0):
    """What-if shocks as fractions (0.10 = +10%). fx_pct > 0 means the rand weakens."""
    return replace(
        p,
        direct_freight_usd=p.direct_freight_usd * (1 + freight_pct),
        inbound_freight_usd=p.inbound_freight_usd * (1 + freight_pct),
        direct_customs_ins_usd=p.direct_customs_ins_usd * (1 + customs_pct),
        inbound_customs_ins_usd=p.inbound_customs_ins_usd * (1 + customs_pct),
        rent_usd_month=p.rent_usd_month * (1 + lease_pct),
        fx_zar_per_usd=p.fx_zar_per_usd * (1 + fx_pct),
    )
#This allows the user to change the values , to simulate different what-if scenarios.

def sensitivity(p: RegionInputs, shock: float = 0.10):
    """Break-even when each input moves by -shock / +shock; sorted by swing."""
    rows = []
    for f in fields(p):
        base = getattr(p, f.name)
        if base == 0:
            continue
        lo = break_even_volume(replace(p, **{f.name: base * (1 - shock)}))
        hi = break_even_volume(replace(p, **{f.name: base * (1 + shock)}))
        swing = abs(hi - lo) if lo is not None and hi is not None else float("inf")
        rows.append({"name": f.name, "label": f.metadata["label"], "low": lo, "high": hi, "swing": swing})
    return sorted(rows, key=lambda r: r["swing"], reverse=True)
# This function calculates the break-even volume for both the lower and upper bounds of each input. 
# This helps identify which inputs have the most significant impact on the break-even point.
#The shock is the default value of 10% and can be changed to see how sensitive the break-even point is to changes in each input.

def progress_to_break_even(q: float, be: Optional[float]):
    if not be:
        return None
    else:
        return  q / be

#This function calculates how far away Fintr is from reaching the break-even point (in order to build a warehouse in either region).