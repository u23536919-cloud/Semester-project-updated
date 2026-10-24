"""Unit tests: results checked against hand-worked examples."""
import pytest
from dataclasses import replace
from models.breakeven import *

# Hand example: v_d = 10 + 2 + 0 = 12 ; v_w = 3 + 2 + 1 + 3 + 0 = 9 ; F_w = 1000+1500+500 = 3000
# Q* = 3000 / (12 - 9) = 1000 units/month
SIMPLE = RegionInputs(
    direct_freight_usd=10, direct_customs_ins_usd=2, sa_handling_zar=0,
    inbound_freight_usd=3, inbound_customs_ins_usd=2, pick_pack_usd=1, local_delivery_usd=3,
    holding_rate_annual=0, setup_usd=0, inbound_shipment_fixed_usd=0,
    rent_usd_month=1000, staff_usd_month=1500, admin_usd_month=500)


def test_variable_and_fixed_costs():
    assert direct_variable_cost(SIMPLE) == 216
    assert warehouse_variable_cost(SIMPLE) == 162
    assert warehouse_fixed_cost(SIMPLE) == 54000


def test_break_even_hand_calculation():
    assert break_even_volume(SIMPLE) == pytest.approx(1000)


def test_costs_equal_at_break_even():
    q = break_even_volume(SIMPLE)
    assert total_cost_direct(SIMPLE, q) == pytest.approx(total_cost_warehouse(SIMPLE, q)) == pytest.approx(216000)


def test_eoq_matches_tutorial_worked_example():
    assert calculate_eoq(12000, 50, 2) == pytest.approx(774.6, abs=0.05)
    assert orders_per_year(12000, calculate_eoq(12000, 50, 2)) == pytest.approx(15.49, abs=0.01)
    assert total_annual_cost(12000, 50, 2, calculate_eoq(12000, 50, 2)) == pytest.approx(1549.19, abs=0.01)


def test_eoq_is_the_minimum_cost_order_quantity():
    q = calculate_eoq(12000, 50, 2)
    best = total_annual_cost(12000, 50, 2, q)
    assert all(total_annual_cost(12000, 50, 2, x) >= best for x in (q * 0.5, q * 0.9, q * 1.1, q * 2))


def test_eoq_rejects_zero_holding_cost():
    with pytest.raises(ModelError):
        calculate_eoq(100, 10, 0)


def test_safety_holding_cost_hand_calculation():
    # H = 0.12*180 = 21.6 ZAR ; (21.6/12) * 1.65 * 0.3 * sqrt(1) = 0.891
    p = replace(SIMPLE, unit_cost_zar=180, holding_rate_annual=0.12, lead_time_months=1.0)
    assert annual_holding_cost_per_unit(p) == pytest.approx(21.6)
    assert safety_holding_cost_per_unit(p) == pytest.approx(0.891)


def test_reorder_point_and_safety_stock():
    p = replace(SIMPLE, lead_time_months=1.0)  # z=1.65, cv=0.3
    assert safety_stock(p, 1000) == pytest.approx(495)
    assert reorder_point(p, 1000) == pytest.approx(1495)


def test_break_even_with_eoq_replenishment():
    # H = 0.15*180 = 27 ; S = 400*18 = 7200 ; k = sqrt(7200*27/6) = 180
    # a = 3*18 = 54 ; F = 3000*18 = 54000 (z = 0); Q* = (100/3)^2 = 1111.11
    p = replace(SIMPLE, unit_cost_zar=180, holding_rate_annual=0.15, service_z=0, inbound_shipment_fixed_usd=400)
    assert cycle_cost_coefficient(p) == pytest.approx(180)
    q = break_even_volume(p)
    assert q == pytest.approx(10000 / 9)
    assert total_cost_direct(p, q) == pytest.approx(total_cost_warehouse(p, q))


def test_replenishment_plan_hand_calculation():
    # D = 12000 ; EOQ = sqrt(2*12000*400/1.5) = 2529.82 ; orders/yr = 4.743 ; 365/4.743 = 76.95 days
    p = replace(SIMPLE, unit_cost_zar=180, holding_rate_annual=0.15, service_z=0, inbound_shipment_fixed_usd=400)
    plan = replenishment_plan(p, 1000)
    assert plan["eoq"] == pytest.approx(2529.82, abs=0.01)
    assert plan["orders_per_year"] == pytest.approx(4.743, abs=0.001)
    assert plan["days_between"] == pytest.approx(76.95, abs=0.05)


def test_fixed_cost_includes_amortised_setup():
    assert warehouse_fixed_cost(replace(SIMPLE, setup_usd=3600, amortisation_months=36)) == pytest.approx(55800)


def test_no_break_even_when_warehouse_not_cheaper_per_unit():
    p = replace(SIMPLE, local_delivery_usd=6)  # v_w = 12 = v_d
    assert break_even_volume(p) is None
    assert recommend(p, 99999) == "Ship from SA"


def test_recommendation_bands():
    assert recommend(SIMPLE, 900) == "Ship from SA"
    assert recommend(SIMPLE, 1050) == "Review: inside margin"
    assert recommend(SIMPLE, 1100) == "Use warehouse"
    assert decision_threshold(SIMPLE) == pytest.approx(1100)


def test_freight_increase_lowers_break_even():
    shocked = apply_scenario(SIMPLE, freight_pct=0.10)  # v_d = 11+2 = 13 ; v_w = 3.3+2+1+3 = 9.3
    assert break_even_volume(shocked) == pytest.approx(3000 / (13 - 9.3))
    assert break_even_volume(shocked) < break_even_volume(SIMPLE)


def test_lease_increase_raises_break_even():
    assert break_even_volume(apply_scenario(SIMPLE, lease_pct=0.10)) == pytest.approx(3100 / 3)


def test_weaker_rand_increases_zar_cost_of_usd_inputs():
    p = replace(SIMPLE, sa_handling_zar=36)
    assert direct_variable_cost(p) == pytest.approx(252)
    assert direct_variable_cost(apply_scenario(p, fx_pct=1.0)) == pytest.approx(468)


def test_sensitivity_sorted_and_complete():
    rows = sensitivity(SIMPLE)
    assert rows[0]["swing"] >= rows[-1]["swing"]
    assert "rent_usd_month" in {r["name"] for r in rows}


def test_cost_curve_shape():
    c = cost_curve(SIMPLE, 2000, points=5)
    assert [r["q"] for r in c] == [0, 500, 1000, 1500, 2000]
    assert c[0]["direct"] == 0 and c[0]["warehouse"] == 54000


def test_saving_and_progress():
    assert monthly_saving(SIMPLE, 2000) == pytest.approx(54000)
    assert progress_to_break_even(800, 1000) == pytest.approx(0.8)


@pytest.mark.parametrize("bad", [{"rent_usd_month": -1}, {"fx_zar_per_usd": 0}, {"amortisation_months": 0}])
def test_invalid_inputs_rejected(bad):
    with pytest.raises(ModelError):
        replace(SIMPLE, **bad)


def test_negative_volume_rejected():
    with pytest.raises(ModelError):
        total_cost_direct(SIMPLE, -5)
