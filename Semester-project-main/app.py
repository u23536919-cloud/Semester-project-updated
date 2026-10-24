"""We used AI to help build our frontend model.
This values displayed on the dashboard are defualt or dummy values. We have not reieved values from Fintr as of yet.
Step 1 demo server. Pages call the Step 2 model directly; Steps 4-5 replace this with
Blueprints + REST endpoints + MySQL. Login is a visual placeholder (no real auth yet)."""
from collections import OrderedDict
from datetime import date
from dataclasses import fields, replace
from math import isfinite
from io import BytesIO
from flask import Flask, flash, redirect, render_template, request, send_file, session, url_for
from models import breakeven as m
from report_pdf import build_report_pdf

REGIONS = {  
    "uk": {"name": "United Kingdom", "volume": 780, "over": {}},
    "us": {"name": "United States", "volume": 1050, "over": {
        "direct_freight_zar": 297.0, "local_delivery_zar": 93.6, "rent_zar_month": 57600.0}},
}
#The above code displays the default values for the different regions, on the website. The user can change these values on the scenario comparison tabs.

MARGIN = 0.10
DEFAULT_ZAR_PER_USD = 18.0
DEFAULT_ZAR_PER_GBP = 23.5
MAIN_FIELDS = ("direct_freight_zar", "setup_zar", "local_delivery_zar", "rent_zar_month")
INV_FIELDS = [f.name for f in fields(m.RegionInputs) if f.metadata["group"] == m.G_I]
SHIPMENT_COST_FIELD = "inbound_shipment_fixed_zar"
REGIONAL_SHIPMENT_FIELDS = tuple(
    (f"{SHIPMENT_COST_FIELD}_{code}", f"Fixed cost per inbound shipment (S) - {REGIONS[code]['name']}")
    for code in REGIONS
)
CUR = {"uk": {"code": "GBP", "axis": "£", "name": "British pounds"},
       "us": {"code": "USD", "axis": "USD", "name": "US dollars"}}

#The above code displays the default values for the different regions, on the website. The user can change these values on the scenario comparison tabs.

#The def setting_fields() function is used to display the default values for the different inventory and replenishment fields, on the website. 
def setting_fields():
    """Inputs shown on the Settings page: exchange rates, then inventory and replenishment."""
    by_name = {f.name: f for f in fields(m.RegionInputs)}
    out = [{"name": "fx_zar_per_usd", "label": "Exchange rate", "unit": "ZAR per USD", "group": "rates", "default": DEFAULT_ZAR_PER_USD},
           {"name": "zar_per_gbp", "label": "Exchange rate", "unit": "ZAR per GBP", "group": "rates", "default": DEFAULT_ZAR_PER_GBP}]
    #This is displaying the exchange rates, for pounds and dollars.
    
    #This for loop is displaying the default values for the different inventory and replenishment fields, on the website. The user can change these values on the settings page.
    #The inventory and replenishment fields are the different costs associated with shipping and storing products in different regions.
    for n in INV_FIELDS:
        if n == SHIPMENT_COST_FIELD:
            continue
        f = by_name[n]
        out.append({"name": n, "label": f.metadata["label"], "unit": f.metadata["unit"], "group": "inv", "default": f.default})
    shipment = by_name[SHIPMENT_COST_FIELD]

    # This for loop is displaying the default values for the different shipment costs, on the website. The user can change these values on the settings page.
    for name, label in REGIONAL_SHIPMENT_FIELDS:
        code = name.rsplit("_", 1)[-1]
        unit = "GBP" if code == "uk" else "USD"
        rate = DEFAULT_ZAR_PER_GBP if code == "uk" else DEFAULT_ZAR_PER_USD
        out.append({"name": name, "label": label, "unit": unit, "group": "regional",
                    "default": shipment.default / rate})
    return out


# The def settings_values() function is used to display the default values but the user can change the values.
# The function will the update to use the new values.
def settings_values():
    """Saved assumptions (kept in the user's session) on top of the defaults."""
    vals = {f["name"]: f["default"] for f in setting_fields()}
    regional_names = {name for name, _ in REGIONAL_SHIPMENT_FIELDS}
    for name, _ in REGIONAL_SHIPMENT_FIELDS:
        vals[name] = m.RegionInputs.inbound_shipment_fixed_zar
    saved = session.get("assump", {})
    vals.update({k: v for k, v in saved.items() if k in vals and k not in regional_names})
    fx = vals["fx_zar_per_usd"]
    legacy = saved.get("inbound_shipment_fixed_usd")
    for code in REGIONS:
        name = f"{SHIPMENT_COST_FIELD}_{code}"
        old_name = f"inbound_shipment_fixed_usd_{code}"
        if name in saved:
            vals[name] = saved[name]
        elif old_name in saved:
            vals[name] = saved[old_name] * fx
        elif legacy is not None:
            vals[name] = legacy * fx
    return vals


# The def region_state() function is used to display the state we in.
def region_state(code):
    state = dict(session.get("state", {}).get(code, {}))
    fx = settings_values()["fx_zar_per_usd"]
    legacy_fields = {
        "direct_freight_usd": "direct_freight_zar",
        "setup_usd": "setup_zar",
        "local_delivery_usd": "local_delivery_zar",
        "rent_usd_month": "rent_zar_month",
    }
    for old_name, name in legacy_fields.items():
        if old_name in state and name not in state:
            state[name] = state[old_name] * fx
    return state


#in the def region_inputs() function, we are displaying the default values for the different regions, on the website. The user can change these values on the scenario comparison tabs.
def region_inputs(code):
    settings = settings_values()

# the values variable is used to store the default values for the different regions, on the website.
    values = {
        **REGIONS[code]["over"],
        **{
            name: settings[name]
            for name in INV_FIELDS if name != SHIPMENT_COST_FIELD
        },
    }

#the shipment_cost variable is used to store the default values for the different shipment costs, on the website.
    shipment_cost = settings[f"{SHIPMENT_COST_FIELD}_{code}"]
    values[SHIPMENT_COST_FIELD] = shipment_cost

#whatever the user inputs the code will overwite the default value with the user input.
    values.update({
        name:value
        for name, value in region_state(code).items()
        if name in MAIN_FIELDS
    })

    return m.RegionInputs(**values)


# the def region volume function updates the volume of the specific region with whatever the user inputs it as.
def region_volume(code):
    return region_state(code).get("volume", REGIONS[code]["volume"])


# The def display_rate() function converts ZAR inputs to the currency shown on that region page.
def display_rate(code):
    """Convert ZAR model inputs to the currency shown on that region page."""
    s = settings_values()
    return 1 / s["zar_per_gbp"] if code == "uk" else 1 / s["fx_zar_per_usd"]

# def freight_change works  out how much the freight rate has changed (in %) compared to the starting value.
def freight_change(code):
    """% change of the current freight rate (saved input and freight slider) against the starting rate."""
    st = region_state(code)
    #base is the starting freight rate.
    base = REGIONS[code]["over"].get("direct_freight_zar", m.RegionInputs.direct_freight_zar)
    if not st or not base:
        return 0.0 #If nothing has been inputted, the freight rate change will be 0.
    #if the user has inputted a new freight rate, the function will calculate the % change of the current freight rate against the starting rate.
    return (st["direct_freight_zar"] * (1 + st.get("wi", {}).get("freight", 0) / 100) / base - 1) * 100


#This function groups the models fields by their metadata group, so that they can be displayed in the settings page in a more organized way.
def grouped_fields():
    groups = OrderedDict()
    for f in fields(m.RegionInputs):
        groups.setdefault(f.metadata["group"], []).append(f) #make the group if its new, then add the field.
    return groups


#This function sets up the Flask app and all the pages (routes) inside it. 
def create_app():
    app = Flask(__name__)
    app.secret_key = "dev-only-change-me" 

    
    @app.template_filter("n")
    def n(v, d=0):
        return "n/a" if v is None else f"{v:,.{d}f}"

    @app.route("/")
    def index():
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            session["name"] = request.form.get("name", "").strip()[:60]
            session["role"] = request.form.get("role", "")[:40]
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    #This function collects the key numbers for one region (break-even, cost per unit, progress and recommendations)
    def summary(code):
        p, q = region_inputs(code), region_volume(code)
        be = m.break_even_volume(p)
        return {"code": code, "name": REGIONS[code]["name"], "q": q, "be": be,
                "direct_unit": m.total_cost_direct(p, q) / q if q else None,
                "wh_unit": m.total_cost_warehouse(p, q) / q if q else None,
                "progress": m.progress_to_break_even(q, be), "rec": m.recommend(p, q, MARGIN)}


    #This functions creates the list of alert messages on the alerts and monitoring page.
    def active_alerts():
        out = []
        #go through the regions and check if they are approaching or have reached break-even, and add an alert message to the list if they are.
        for r in sorted((summary(c) for c in REGIONS), key=lambda r: r["progress"] or 0, reverse=True):
            pct = round((r["progress"] or 0) * 100)
            if r["be"] is None:
                out.append(f"{r['name']}: warehouse costs more per unit than direct shipping, so there is no break-even")
            elif pct >= 100:
                out.append(f"{r['name']} has reached break-even: review regional warehousing")
            elif pct >= 80:
                out.append(f"{r['name']} approaching break-even threshold")
        #check if the freight rate changed and add an alert message to the alerts page if it did.
        for code in REGIONS:
            ch = freight_change(code)
            if abs(ch) >= 0.05:
                amount = f"{abs(ch):.1f}".rstrip("0").rstrip(".") # removes the spaces and trailing zeros from the number, so that it looks cleaner on the page.
                out.append(f"{code.upper()} freight rate {'increased' if ch > 0 else 'decreased'} {amount}%")
        return out

    
    #shell() adds the users name , role and alert count to every template automatically, so we dont have to enetr them manually on every page.
    @app.context_processor
    def shell():
        return {"user_name": session.get("name", ""), "user_role": session.get("role", ""),
                "alert_count": len(active_alerts())}

    #overview() works out the combined UK + US numbers for the dashboard
    def overview():
        """Combined UK + US picture. Total volume is split between regions in today's proportions;
        each region keeps its own warehouse, so costs are summed region by region."""
        parts = [(region_inputs(c), region_volume(c)) for c in REGIONS]
        # The total variable is used to store the total volume of all regions combined, and the tot variable is used to store the total volume or 1 if the total volume is 0.
        total = sum(q for _, q in parts)
        tot = total or 1

        #adds up a cost function across both regions, giving each region its share volume-
        
        def cost(fn, vol):
            return sum(fn(p, vol * q / tot) for p, q in parts) 

        def gap(vol):  # warehouse minus direct: positive means shipping from SA is cheaper
            return cost(m.total_cost_warehouse, vol) - cost(m.total_cost_direct, vol)

        be = None
        hi = max(total, 1.0)

        while gap(hi) > 0 and hi < 1e7: 
            hi *= 2
        if gap(hi) <= 0:
            lo = 0.0
            for _ in range(60):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if gap(mid) > 0 else (lo, mid)
            be = hi

        top = max(total * 1.3, (be or 0) * 1.5, 100)
        pts = 12
        curve = [{"q": round(i * top / pts), "direct": cost(m.total_cost_direct, i * top / pts) / 1000,
                  "warehouse": cost(m.total_cost_warehouse, i * top / pts) / 1000} for i in range(pts + 1)]
        kpi = {"volume": total,
               "direct_zar": cost(m.total_cost_direct, total) / total if total else None,
               "wh_zar": cost(m.total_cost_warehouse, total) / total if total else None, "be": be}
        return kpi, curve

    @app.route("/dashboard")
    def dashboard():
        kpi, curve = overview()
        return render_template("dashboard.html", kpi=kpi, curve=curve, page="dashboard",
                               updated=date.today().strftime("%d %b %Y"))

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        fields_ = setting_fields()
        if request.method == "POST":
            if "reset" in request.form:
                session.pop("assump", None)
                flash("Assumptions reset to the defaults.", "success")
                return redirect(url_for("settings"))
            try:
                new = {}
                for f in fields_:
                    v = float(request.form[f["name"]])
                    name, where = f["name"], f"{f['label']} ({f['unit']})" if f["group"] == "rates" else f["label"]
                    if not isfinite(v) or v < 0:
                        raise m.ModelError(f"{where} must be a number of 0 or more.")
                    if name in ("fx_zar_per_usd", "zar_per_gbp", "unit_cost_zar", "holding_rate_annual") and v <= 0:
                        raise m.ModelError(f"{where} must be above 0.")
                    if name == "holding_rate_annual" and v > 1:
                        raise m.ModelError(f"{where} must be between 0 and 1.")
                    new[name] = v
                current = settings_values()
                for code in REGIONS:
                    name = f"{SHIPMENT_COST_FIELD}_{code}"
                    old_rate = current["zar_per_gbp"] if code == "uk" else current["fx_zar_per_usd"]
                    if abs(new[name] - round(current[name] / old_rate, 2)) < 0.005:
                        new[name] = current[name]
                    else:
                        rate = new["zar_per_gbp"] if code == "uk" else new["fx_zar_per_usd"]
                        new[name] *= rate
                model_fields = {f.name for f in fields(m.RegionInputs)}
                m.RegionInputs(**{k: v for k, v in new.items() if k in model_fields})
                session["assump"] = new
                flash("Assumptions saved.", "success")
                return redirect(url_for("settings"))
            except (ValueError, KeyError) as e:
                flash(str(e) if isinstance(e, m.ModelError) else "Enter a number in every assumption field.", "danger")
        vals = settings_values()
        regional = []
        for f in fields_:
            if f["group"] != "regional":
                continue
            code = f["name"].rsplit("_", 1)[-1]
            rate = vals["zar_per_gbp"] if code == "uk" else vals["fx_zar_per_usd"]
            regional.append(dict(f, value=round(vals[f["name"]] / rate, 2)))
        return render_template("settings.html", page="settings", margin=int(MARGIN * 100),
                               rates=[dict(f, value=vals[f["name"]]) for f in fields_ if f["group"] == "rates"],
                               inv=[dict(f, value=vals[f["name"]]) for f in fields_ if f["group"] == "inv"],
                               regional=regional)

    @app.route("/alerts")
    def alerts():
        rows = sorted((summary(c) for c in REGIONS), key=lambda r: r["progress"] or 0, reverse=True)
        return render_template("alerts.html", rows=rows, alerts=active_alerts(), page="alerts")

    ANALYSIS = [("be", "Break even volume"), ("cost", "Current vs Alternative cost"),
                ("savings", "Potential savings"), ("rec", "Recommendation")]

    def report_data(code, show):
        """Everything the report preview and the PDF need, so both always say the same thing."""
        p, q = region_inputs(code), region_volume(code)
        s = summary(code)
        saving, threshold = m.monthly_saving(p, q), m.decision_threshold(p, MARGIN)
        if s["be"] is None:
            text = "The warehouse costs more per unit than direct shipping, so volume alone will not make it cheaper."
        else:
            text = (f"Current volume is {q:,.0f} units per month, which is {round((s['progress'] or 0) * 100)}% of the "
                    f"break-even volume of {s['be']:,.0f}. With a {int(MARGIN * 100)}% margin, the decision "
                    f"threshold is {threshold:,.0f}.")
        text += (f" At the current volume a regional warehouse would save about ZAR {saving:,.0f} per month."
                 if saving >= 0 else
                 f" At the current volume a regional warehouse would cost about ZAR {-saving:,.0f} more per month "
                 f"than shipping from SA.")
        who = " - ".join(x for x in (session.get("name", ""), session.get("role", "")) if x)
        return {"region": s["name"], "date": date.today().strftime("%d %b %Y"), "user": who, "show": show,
                "labels": [label for key, label in ANALYSIS if key in show], "q": q, "be": s["be"], "saving": saving,
                "direct": m.total_cost_direct(p, q), "warehouse": m.total_cost_warehouse(p, q), "rec": s["rec"],
                "rec_text": text, "threshold": threshold, "s": s}

    def report_args():
        code = request.args.get("region", "uk")
        code = code if code in REGIONS else "uk"
        # "f" is sent by the form; without it (first visit) every analysis option is shown
        keys = {k for k, _ in ANALYSIS}
        show = {k for k in request.args.getlist("show") if k in keys} if request.args.get("f") else keys
        return code, show

    @app.route("/reports")
    def reports():
        code, show = report_args()
        d = report_data(code, show)
        return render_template("reports.html", d=d, s=d["s"], regions=REGIONS, code=code, page="reports", show=show,
                               saving=d["saving"], costs={"direct": d["direct"], "warehouse": d["warehouse"]},
                               analysis=ANALYSIS, generated=bool(request.args.get("g")), today=d["date"])

    @app.route("/reports/pdf")
    def reports_pdf():
        code, show = report_args()
        if not show:
            flash("Select at least one analysis option before exporting.", "warning")
            return redirect(url_for("reports", region=code, f=1))
        d = report_data(code, show)
        name = f"Fintr_report_{code.upper()}_{date.today().isoformat()}.pdf"
        return send_file(BytesIO(build_report_pdf(d)), mimetype="application/pdf", as_attachment=True,
                         download_name=name)

    def build_results(p, vol, wi):
        """Everything the region page shows; all model costs are in ZAR."""
        sp = m.apply_scenario(p, wi["freight"] / 100, wi["customs"] / 100, wi["lease"] / 100)
        sq = vol * (1 + wi["growth"] / 100)
        be = m.break_even_volume(p)
        base_saving = m.monthly_saving(p, vol)

        def row(label, pp, qq, base=False):
            # change in the monthly saving from a warehouse versus the base case (+ favours the warehouse)
            impact = None if base else m.monthly_saving(pp, qq) - base_saving
            return {"label": label, "be": m.break_even_volume(pp), "impact": impact,
                    "rec": m.recommend(pp, qq, MARGIN)}

        scen = [row("Base case", p, vol, base=True),
                row("Freight rate +10%", m.apply_scenario(p, freight_pct=0.10), vol),
                row("Freight rate -10%", m.apply_scenario(p, freight_pct=-0.10), vol),
                row("Volume growth +10%", p, vol * 1.10),
                row("Volume growth -10%", p, vol * 0.90),
                row("Warehouse lease +10%", m.apply_scenario(p, lease_pct=0.10), vol),
                row("Warehouse lease -10%", m.apply_scenario(p, lease_pct=-0.10), vol)]
        if any(wi.values()):
            scen.append(row("Your what-if (sliders)", sp, sq))
        top = max(vol, sq, (be or 0) * 1.5, 100)
        return {"be": be, "threshold": m.decision_threshold(p, MARGIN), "rec": m.recommend(p, vol, MARGIN),
                "saving": m.monthly_saving(p, vol), "curve": m.cost_curve(p, top, 13), "scen": scen}

    @app.route("/region/<code>", methods=["GET", "POST"])
    def region(code):
        if code not in REGIONS:
            return render_template("error.html", msg="That region is not set up yet."), 404
        rate = display_rate(code)  # ZAR -> region currency
        p, vol = region_inputs(code), region_volume(code)
        wi = {k: region_state(code).get("wi", {}).get(k, 0) for k in ("freight", "customs", "lease", "growth")}
        calc = None
        if request.method == "POST":
            try:
                new = {}
                for k in MAIN_FIELDS:  # a value left as displayed keeps its exact stored amount (no rounding drift)
                    shown, now = float(request.form[k]), getattr(p, k)
                    new[k] = now if abs(shown - round(now * rate, 2)) < 0.005 else shown / rate
                nvol = float(request.form["volume"])
                nwi = {k: float(request.form.get("wi_" + k, 0)) for k in wi}
                if not all(isfinite(v) for v in [nvol, *nwi.values(), *new.values()]):
                    raise m.ModelError("Enter numbers only.")
                np_ = replace(p, **new)
                calc = build_results(np_, nvol, nwi)
                p, vol, wi = np_, nvol, nwi
                state = session.get("state", {})
                state[code] = {**{k: getattr(p, k) for k in MAIN_FIELDS}, "volume": vol, "wi": wi}
                session["state"] = state
            except (ValueError, KeyError) as e:
                flash(str(e) if isinstance(e, m.ModelError) else "Check every field: enter numbers only.", "danger")
        if calc is None:
            calc = build_results(p, vol, wi)
        vals = {k: round(getattr(p, k) * rate, 2) for k in MAIN_FIELDS}
        return render_template("region.html", code=code, name=REGIONS[code]["name"], vals=vals, vol=vol, wi=wi,
                               cur=CUR[code], page=code, margin=int(MARGIN * 100), calc=calc)

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
