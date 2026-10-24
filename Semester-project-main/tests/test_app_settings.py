from app import REGIONAL_SHIPMENT_FIELDS, create_app, region_inputs, setting_fields
from flask import session
import pytest


def test_settings_page_shows_region_currency_but_uses_zar_field_names():
    app = create_app()
    response = app.test_client().get("/settings")

    assert response.status_code == 200
    for name, _ in REGIONAL_SHIPMENT_FIELDS:
        assert f'name="{name}"'.encode() in response.data
    assert b'name="inbound_shipment_fixed_zar"' not in response.data
    assert b"(GBP)" in response.data
    assert b"(USD)" in response.data
    assert b'value="459.57"' in response.data
    assert b'value="600.0"' in response.data


def test_region_inputs_use_region_specific_zar_shipment_costs():
    app = create_app()
    with app.test_request_context():
        session["assump"] = {
            "inbound_shipment_fixed_zar_uk": 450 * 23.5,
            "inbound_shipment_fixed_zar_us": 700 * 18,
        }

        assert region_inputs("uk").inbound_shipment_fixed_zar == pytest.approx(450 * 23.5)
        assert region_inputs("us").inbound_shipment_fixed_zar == 700 * 18


def test_region_pages_display_zar_defaults_in_local_currency():
    app = create_app()
    client = app.test_client()

    uk_response = client.get("/region/uk")
    us_response = client.get("/region/us")

    assert b'name="direct_freight_zar"' in uk_response.data
    assert b'value="10.72"' in uk_response.data
    assert b'value="16.5"' in us_response.data


def test_settings_form_saves_shipment_costs_in_zar():
    app = create_app()
    client = app.test_client()
    data = {field["name"]: str(field["default"]) for field in setting_fields()}
    data["inbound_shipment_fixed_zar_uk"] = "450"
    data["inbound_shipment_fixed_zar_us"] = "700"

    response = client.post("/settings", data=data)

    assert response.status_code == 302
    with client.session_transaction() as saved:
        assert saved["assump"]["inbound_shipment_fixed_zar_uk"] == 450 * 23.5
        assert saved["assump"]["inbound_shipment_fixed_zar_us"] == 700 * 18


def test_unchanged_rounded_shipment_costs_keep_exact_zar_values():
    app = create_app()
    client = app.test_client()
    data = {field["name"]: str(field["default"]) for field in setting_fields()}

    response = client.post("/settings", data=data)

    assert response.status_code == 302
    with client.session_transaction() as saved:
        assert saved["assump"]["inbound_shipment_fixed_zar_uk"] == 10800
        assert saved["assump"]["inbound_shipment_fixed_zar_us"] == 10800


def test_region_inputs_are_displayed_in_local_currency_but_saved_in_zar():
    app = create_app()
    client = app.test_client()

    response = client.post("/region/uk", data={
        "direct_freight_zar": "10",
        "setup_zar": "100",
        "local_delivery_zar": "3",
        "rent_zar_month": "1000",
        "volume": "780",
    })

    assert response.status_code == 200
    with client.session_transaction() as saved:
        state = saved["state"]["uk"]
        assert state["direct_freight_zar"] == pytest.approx(10 * 23.5)
        assert state["setup_zar"] == pytest.approx(100 * 23.5)
        assert state["local_delivery_zar"] == pytest.approx(3 * 23.5)
        assert state["rent_zar_month"] == pytest.approx(1000 * 23.5)


def test_legacy_usd_session_values_are_migrated_to_zar():
    app = create_app()
    with app.test_request_context():
        session["assump"] = {
            "fx_zar_per_usd": 20,
            "inbound_shipment_fixed_usd_uk": 450 * 23.5 / 18,
        }
        session["state"] = {"uk": {"direct_freight_usd": 10}}

        assert region_inputs("uk").inbound_shipment_fixed_zar == pytest.approx(450 * 23.5 / 18 * 20)
        assert region_inputs("uk").direct_freight_zar == 200
