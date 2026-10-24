"""Builds the one-page PDF report from the Reporting and export tab (uses ReportLab)."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PURPLE, YELLOW = colors.HexColor("#7e5594"), colors.HexColor("#fffe77")
BLUE, LILAC, GREY = colors.HexColor("#4a7df0"), colors.HexColor("#9a78d6"), colors.HexColor("#9a9a9a")
WIDTH = A4[0] - 36 * mm  # usable width inside the margins

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.5, leading=11, textColor=colors.HexColor("#444444"))
H2 = ParagraphStyle("h2", parent=BODY, fontName="Helvetica-Bold", fontSize=12, leading=15, spaceBefore=14, spaceAfter=6)
TITLE = ParagraphStyle("title", parent=BODY, fontName="Helvetica-Bold", fontSize=20, leading=24)
CELL = ParagraphStyle("cell", parent=BODY, alignment=1, leading=17)


def _money(v):
    return f"{v:,.0f}"


def _key_figures(d):
    cells = []
    if "be" in d["show"]:
        be = "n/a" if d["be"] is None else _money(d["be"])
        cells += [("Break Even Volume", be, "units/month"), ("Current Volume", _money(d["q"]), "units/month")]
    if "savings" in d["show"]:
        note = f"ZAR/month (warehouse costs {_money(-d['saving'])} more)" if d["saving"] < 0 else "ZAR/month"
        cells.append(("Potential Savings", _money(max(d["saving"], 0)), note))
    if not cells:
        return None
    paras = [Paragraph(f'<font size="8.5">{escape(a)}</font><br/><font size="17"><b>{escape(b)}</b></font><br/>'
                       f'<font size="8">{escape(c)}</font>', CELL) for a, b, c in cells]
    t = Table([paras], colWidths=[WIDTH / len(paras)] * len(paras))
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, GREY), ("INNERGRID", (0, 0), (-1, -1), 0.6, GREY),
                           ("BACKGROUND", (0, 0), (-1, -1), colors.white), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    return t


def _chart(d):
    direct, wh = d["direct"], d["warehouse"]
    dr = Drawing(WIDTH, 190)
    dr.add(String(WIDTH / 2, 176, f"Monthly cost at {_money(d['q'])} units per month (ZAR)", textAnchor="middle",
                  fontName="Helvetica-Bold", fontSize=9))
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 60, 24, WIDTH - 90, 138
    bc.data = [[direct, wh]]
    bc.categoryAxis.categoryNames = ["Ship from SA", "Use warehouse"]
    bc.categoryAxis.labels.fontName = bc.valueAxis.labels.fontName = "Helvetica"
    bc.categoryAxis.labels.fontSize = bc.valueAxis.labels.fontSize = 8.5
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(direct, wh, 1) * 1.2
    bc.valueAxis.labelTextFormat = lambda v: f"{v:,.0f}"
    bc.valueAxis.gridStrokeColor = colors.HexColor("#dddddd")
    bc.valueAxis.visibleGrid = True
    bc.barWidth = 40
    bc.groupSpacing = 40
    bc.bars[(0, 0)].fillColor = BLUE
    bc.bars[(0, 1)].fillColor = LILAC
    bc.barLabelFormat = lambda v: f"{v:,.0f}"
    bc.barLabels.nudge = 8
    bc.barLabels.fontName, bc.barLabels.fontSize = "Helvetica-Bold", 8.5
    dr.add(bc)
    return dr


def _cost_table(d):
    q = d["q"] or 1
    diff = d["warehouse"] - d["direct"]
    rows = [["Option", "Monthly cost (ZAR)", "Cost per unit (ZAR)"],
            ["Ship from SA", _money(d["direct"]), f"{d['direct'] / q:,.2f}"],
            ["Use warehouse", _money(d["warehouse"]), f"{d['warehouse'] / q:,.2f}"],
            ["Warehouse minus SA", f"{'+' if diff >= 0 else '-'}{_money(abs(diff))}", f"{diff / q:+,.2f}"]]
    t = Table(rows, colWidths=[WIDTH * 0.4, WIDTH * 0.3, WIDTH * 0.3])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9), ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efefef")),
                           ("GRID", (0, 0), (-1, -1), 0.5, GREY), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _footer(d):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(GREY)
        canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#444444"))
        canvas.drawString(18 * mm, 10.5 * mm, f"Fintr break-even decision model  |  Generated {d['date']}")
        canvas.drawRightString(A4[0] - 18 * mm, 10.5 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def build_report_pdf(d):
    """d: dict with region, date, user, show (set of 'be','cost','savings','rec'), q, be, saving, direct,
    warehouse, rec, rec_text, labels (names of the selected analysis options). Returns the PDF as bytes."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=22 * mm, title=f"Fintr report - {d['region']}", author="Fintr")
    band = Table([[Paragraph("Fintr  |  Regional warehouse break-even report", TITLE)],
                  [Paragraph(f"{escape(d['region'])}  -  {escape(d['date'])}", ParagraphStyle(
                      "sub", parent=BODY, fontSize=11, textColor=PURPLE))]], colWidths=[WIDTH])
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), YELLOW), ("LINEBELOW", (0, -1), (-1, -1), 2, PURPLE),
                              ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (0, 0), 12),
                              ("BOTTOMPADDING", (0, -1), (-1, -1), 10)]))
    story = [band, Spacer(1, 8)]
    if d["user"]:
        story.append(Paragraph(f"Prepared by: {escape(d['user'])}", SMALL))
    story.append(Paragraph(f"Analysis included: {escape(', '.join(d['labels']))}", SMALL))

    kf = _key_figures(d)
    if kf:
        story += [Paragraph("Key Figures", H2), kf]
    if "cost" in d["show"]:
        story += [Paragraph("Current vs Alternative cost", H2), _chart(d), Spacer(1, 4), _cost_table(d)]
    if "rec" in d["show"]:
        story += [Paragraph("Recommendation Summary", H2),
                  Paragraph(f"<b>{escape(d['rec'])}.</b> {escape(d['rec_text'])}", BODY), Spacer(1, 6),
                  Paragraph("Based on the stated assumptions; see the region page for sensitivity results. "
                            "All amounts are in ZAR.", SMALL)]
    doc.build(story, onFirstPage=_footer(d), onLaterPages=_footer(d))
    return buf.getvalue()
