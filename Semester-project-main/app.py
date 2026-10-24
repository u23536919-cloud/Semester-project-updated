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
        "direct_freight_usd": 16.5, "local_delivery_usd": 5.2, "rent_usd_month": 3200.0}},
}
#The above code displays the default values for the different regions, on the website. The user can change these values on the scenario comparison tabs.

MARGIN = 0.10
DEFAULT_ZAR_PER_GBP = 23.5
MAIN_FIELDS = ("direct_freight_usd", "setup_usd", "local_delivery_usd", "rent_usd_month")
INV_FIELDS = [f.name for f in fields(m.RegionInputs) if f.metadata["group"] == m.G_I]
SHIPMENT_COST_FIELD = "inbound_shipment_fixed_usd"
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
    fx = by_name["fx_zar_per_usd"]
    out = [{"name": "fx_zar_per_usd", "label": "Exchange rate", "unit": "ZAR per USD", "group": "rates", "default": fx.default},
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
        unit = "GBP" if code == "uk" else shipment.metadata["unit"]
        out.append({"name": name, "label": label, "unit": unit, "group": "regional",
                    "default": shipment.default})
    return out



def settings_values():
    """Saved assumptions (kept in the user's session) on top of the defaults."""
    vals = {f["name"]: f["default"] for f in setting_fields()}
    saved = session.get("assump", {})
    vals.update({k: v for k, v in saved.items() if k in vals})
    legacy = saved.get(SHIPMENT_COST_FIELD)
    if legacy is not None:
        for code in REGIONS:
            name = f"{SHIPMENT_COST_FIELD}_{code}"
            if name not in saved:
                vals[name] = legacy
    fx = vals["fx_zar_per_usd"]
    zar_per_gbp = vals["zar_per_gbp"]
    vals[f"{SHIPMENT_COST_FIELD}_uk"] = round(vals[f"{SHIPMENT_COST_FIELD}_uk"] * fx / zar_per_gbp, 2)
    return vals


def region_state(code):
    return session.get("state", {}).get(code, {})


def region_inputs(code):
    s = settings_values()
    kw = dict(REGIONS[code]["over"])
    kw.update({k: s[k] for k in ["fx_zar_per_usd"] + [n for n in INV_FIELDS if n != SHIPMENT_COST_FIELD]})
    shipment_cost = s[f"{SHIPMENT_COST_FIELD}_{code}"]
    if code == "uk":
        shipment_cost *= s["zar_per_gbp"] / s["fx_zar_per_usd"]
    kw[SHIPMENT_COST_FIELD] = shipment_cost
    kw.update({k: v for k, v in region_state(code).items() if k in MAIN_FIELDS})
    return m.RegionInputs(**kw)


def region_volume(code):
    return region_state(code).get("volume", REGIONS[code]["volume"])


def display_rate(code):
    """Convert USD-denominated region inputs to the currency shown on that region page."""
    s = settings_values()
    return s["fx_zar_per_usd"] / s["zar_per_gbp"] if code == "uk" else 1.0


def freight_change(code):
    """% change of the current freight rate (saved input and freight slider) against the starting rate."""
    st = region_state(code)
    base = REGIONS[code]["over"].get("direct_freight_usd", m.RegionInputs.direct_freight_usd)
    if not st or not base:
        return 0.0
    return (st["direct_freight_usd"] * (1 + st.get("wi", {}).get("freight", 0) / 100) / base - 1) * 100


def grouped_fields():
    groups = OrderedDict()
    for f in fields(m.RegionInputs):
        groups.setdefault(f.metadata["group"], []).append(f)
    return groups


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

    def summary(code):
        p, q = region_inputs(code), region_volume(code)
        be = m.break_even_volume(p)
        return {"code": code, "name": REGIONS[code]["name"], "q": q, "be": be,
                "direct_unit": m.total_cost_direct(p, q) / q if q else None,
                "wh_unit": m.total_cost_warehouse(p, q) / q if q else None,
                "progress": m.progress_to_break_even(q, be), "rec": m.recommend(p, q, MARGIN)}

    def active_alerts():
        out = []
        for r in sorted((summary(c) for c in REGIONS), key=lambda r: r["progress"] or 0, reverse=True):
            pct = round((r["progress"] or 0) * 100)
            if r["be"] is None:
                out.append(f"{r['name']}: warehouse costs more per unit than direct shipping, so there is no break-even")
            elif pct >= 100:
                out.append(f"{r['name']} has reached break-even: review regional warehousing")
            elif pct >= 80:
                out.append(f"{r['name']} approaching break-even threshold")
        for code in REGIONS:
            ch = freight_change(code)
            if abs(ch) >= 0.05:
                amount = f"{abs(ch):.1f}".rstrip("0").rstrip(".")
                out.append(f"{code.upper()} freight rate {'increased' if ch > 0 else 'decreased'} {amount}%")
        return out

    @app.context_processor
    def shell():
        return {"user_name": session.get("name", ""), "user_role": session.get("role", ""),
                "alert_count": len(active_alerts())}

    def overview():
        """Combined UK + US picture. Total volume is split between regions in today's proportions;
        each region keeps its own warehouse, so costs are summed region by region."""
        parts = [(region_inputs(c), region_volume(c)) for c in REGIONS]
        total = sum(q for _, q in parts)
        tot = total or 1

        def cost(fn, vol):
            return sum(fn(p, vol * q / tot) for p, q in parts)

        def gap(vol):  # warehouse minus direct: positive means shipping from SA is cheaper
            return cost(m.total_cost_warehouse, vol) - cost(m.total_cost_direct, vol)

        be, hi = None, max(total, 1.0)
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
                new[f"{SHIPMENT_COST_FIELD}_uk"] *= new["zar_per_gbp"] / new["fx_zar_per_usd"]
                model_fields = {f.name for f in fields(m.RegionInputs)}
                m.RegionInputs(**{k: v for k, v in new.items() if k in model_fields})
                session["assump"] = new
                flash("Assumptions saved.", "success")
                return redirect(url_for("settings"))
            except (ValueError, KeyError) as e:
                flash(str(e) if isinstance(e, m.ModelError) else "Enter a number in every assumption field.", "danger")
        vals = settings_values()
        return render_template("settings.html", page="settings", margin=int(MARGIN * 100),
                               rates=[dict(f, value=vals[f["name"]]) for f in fields_ if f["group"] == "rates"],
                               inv=[dict(f, value=vals[f["name"]]) for f in fields_ if f["group"] == "inv"],
                               regional=[dict(f, value=vals[f["name"]]) for f in fields_ if f["group"] == "regional"])

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
        rate = display_rate(code)  # USD -> region currency (pounds for the UK)
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
