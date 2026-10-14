"""Tag check: finds duplicate pole / fixture tags in a drawing whose NEW tags are plain text
(e.g. the 'TAGG UPDATED' PDF), marks them on a copy of the PDF and writes an Excel list.
Command line:  python app.py --cli --tagcheck drawing.pdf [--out marked.pdf] [--xlsx list.xlsx]"""
import re, io, collections
import pdfplumber

# tag = PANEL/CCCLn-NN[/CCCLn-NN]  (a stray '-' after the slash is tolerated and reported)
TAG_START = re.compile(r"^[0-9A-Z]{4,10}/-?\d\d")
PART = re.compile(r"^\d\dL[123]-\d\d$")


def _norm(t):
    return re.sub(r"\s+", "", t).strip("-")


def read_tags(path, page_no=0):
    pdf = pdfplumber.open(path)
    pg = pdf.pages[page_no]
    ws = pg.extract_words(extra_attrs=["size"])
    out = []
    for w in ws:
        if not TAG_START.match(w["text"]):
            continue
        below = [v for v in ws if v is not w and 0 < v["top"] - w["top"] < 12 and abs(v["x0"] - w["x0"]) < 14 and v["text"].startswith("LD")]
        out.append(dict(raw=w["text"], tag=_norm(w["text"]), type=(below[0]["text"] if below else ""),
                        x=round((w["x0"] + w["x1"]) / 2), y=round(w["top"]), box=(w["x0"], w["top"], w["x1"], w["bottom"])))
    return out, (pg.width, pg.height), (pg.rotation or 0)


def analyse(tags):
    by = collections.defaultdict(list); fx = collections.defaultdict(list)
    for u in tags:
        by[u["tag"]].append(u)
        parts = u["tag"].split("/")
        for f in parts[1:]:
            fx[parts[0] + "/" + f].append(u)
    pole_dups = {k: v for k, v in by.items() if len(v) > 1}
    fx_dups = {k: v for k, v in fx.items() if len(v) > 1}
    bad = []
    for u in tags:
        parts = u["tag"].split("/")
        why = []
        if "/-" in u["raw"]:
            why.append("stray '-' after the panel name")
        if not all(PART.match(p) for p in parts[1:]):
            why.append("part not like 01L1-05 (circuit/phase/no.)")
        elif len(parts) == 3 and parts[1][:2] != parts[2][:2]:
            why.append("two fixtures from different circuits")
        if len(parts) > 3:
            why.append("more than two fixtures")
        if why:
            bad.append((u, "; ".join(why)))
    return dict(poles=by, fixtures=fx, pole_dups=pole_dups, fx_dups=fx_dups, bad=bad)


def mark_pdf(src, dst, tags, res, view, rotation):
    import pypdf
    from reportlab.pdfgen import canvas
    Wv, Hv = view
    r = pypdf.PdfReader(src); pg = r.pages[0]
    Wu, Hu = float(pg.mediabox.width), float(pg.mediabox.height)
    m = {0: (1, 0, 0, 1, 0, 0), 90: (0, 1, -1, 0, Hv, 0), 180: (-1, 0, 0, -1, Wv, Hv), 270: (0, -1, 1, 0, 0, Wv)}[rotation % 360]
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=(Wu, Hu)); c.transform(*m)
    pd = res["pole_dups"]; fd = res["fx_dups"]; bad = {id(u) for u, _ in res["bad"]}
    for u in tags:
        parts = u["tag"].split("/")
        isp = u["tag"] in pd; isf = any(parts[0] + "/" + f in fd for f in parts[1:]); isb = id(u) in bad
        if not (isp or isf or isb):
            continue
        col = (1, 0, 0) if isp else ((1, 0.5, 0) if isf else (1, 0, 1))
        x0, t, x1, b = u["box"]
        c.setStrokeColorRGB(*col); c.setLineWidth(1.8 if isp else 1.2)
        cx = (x0 + x1) / 2; cy = Hv - ((t + b) / 2 + 3.5)
        c.ellipse(cx - (x1 - x0) / 2 - 10, cy - 14, cx + (x1 - x0) / 2 + 10, cy + 14)
    lx, ly = 60, Hv - 60
    c.setFillColorRGB(0, 0, 0); c.setFont("Helvetica-Bold", 22); c.drawString(lx, ly, "TAG CHECK")
    for i, (col, txt) in enumerate([((1, 0, 0), "Red: same POLE tag on two poles"), ((1, 0.5, 0), "Orange: fixture tag also used on another pole"),
                                    ((1, 0, 1), "Magenta: suspicious tag (format / mixed circuits)")]):
        c.setStrokeColorRGB(*col); c.setLineWidth(3); c.ellipse(lx, ly - 45 - i * 32, lx + 36, ly - 25 - i * 32)
        c.setFillColorRGB(0, 0, 0); c.setFont("Helvetica", 18); c.drawString(lx + 48, ly - 40 - i * 32, txt)
    c.save(); buf.seek(0)
    pg.merge_page(pypdf.PdfReader(buf).pages[0])
    w = pypdf.PdfWriter(); w.add_page(pg); w.write(dst)


def export_xlsx(path, res):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()

    def sheet(ws, head, rows):
        ws.append(head)
        for c in ws[1]:
            c.font = Font(bold=True, name="Arial"); c.fill = PatternFill("solid", fgColor="DDEBF7")
        for r in rows:
            ws.append(r)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = max(12, min(48, max(len(str(c.value or "")) for c in col) + 2))
        ws.freeze_panes = "A2"
    ws = wb.active; ws.title = "Duplicate pole tags"
    sheet(ws, ["Pole tag", "Occurrence", "Fixture type", "X", "Y", "Note"],
          [[k, i + 1, u["type"], u["x"], u["y"], "type differs" if len({x["type"].split("-")[0] for x in v}) > 1 else ""]
           for k, v in sorted(res["pole_dups"].items()) for i, u in enumerate(v)])
    sheet(wb.create_sheet("Duplicate fixture tags"), ["Fixture tag", "Poles carrying it", "Pole tag", "Fixture type", "X", "Y"],
          [[k, len(v), u["tag"], u["type"], u["x"], u["y"]] for k, v in sorted(res["fx_dups"].items()) for u in v])
    sheet(wb.create_sheet("Suspicious tags"), ["Pole tag as drawn", "Problem", "Fixture type", "X", "Y"],
          [[u["raw"], why, u["type"], u["x"], u["y"]] for u, why in sorted(res["bad"], key=lambda t: t[0]["tag"])])
    wb.save(path)


def run(pdf, out_pdf=None, out_xlsx=None):
    tags, view, rot = read_tags(pdf)
    res = analyse(tags)
    if out_pdf:
        mark_pdf(pdf, out_pdf, tags, res, view, rot)
    if out_xlsx:
        export_xlsx(out_xlsx, res)
    msg = (f"{len(tags)} pole tags read; {len(res['pole_dups'])} pole tags used twice; "
           f"{len(res['fx_dups'])} fixture tags on more than one pole; {len(res['bad'])} suspicious tags.")
    return res, msg
