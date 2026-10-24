from app import REGIONAL_SHIPMENT_FIELDS, create_app, region_inputs, setting_fields
from flask import session
import pytest


def test_settings_page_has_separate_inbound_shipment_fields():
    app = create_app()
    response = app.test_client().get("/settings")

    assert response.status_code == 200
    for name, _ in REGIONAL_SHIPMENT_FIELDS:
        assert f'name="{name}"'.encode() in response.data
    assert b'name="inbound_shipment_fixed_usd"' not in response.data
    assert b"(GBP)" in response.data
    assert b"(USD)" in response.data
    assert b'value="459.57"' in response.data


def test_region_inputs_use_region_specific_shipment_costs():
    app = create_app()
    with app.test_request_context():
        session["assump"] = {
            "inbound_shipment_fixed_usd_uk": 450 * 23.5 / 18,
            "inbound_shipment_fixed_usd_us": 700,
        }

        assert region_inputs("uk").inbound_shipment_fixed_usd == pytest.approx(450 * 23.5 / 18)
        assert region_inputs("us").inbound_shipment_fixed_usd == 700


def test_settings_form_saves_distinct_shipment_costs():
    app = create_app()
    client = app.test_client()
    data = {field["name"]: str(field["default"]) for field in setting_fields()}
    data["inbound_shipment_fixed_usd_uk"] = "450"
    data["inbound_shipment_fixed_usd_us"] = "700"

    response = client.post("/settings", data=data)

    assert response.status_code == 302
    with client.session_transaction() as saved:
        assert saved["assump"]["inbound_shipment_fixed_usd_uk"] == 450 * 23.5 / 18
        assert saved["assump"]["inbound_shipment_fixed_usd_us"] == 700
