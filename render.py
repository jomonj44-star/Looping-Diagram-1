"""Draws the cover sheet and the looping diagram sheets (matplotlib, vector PDF)."""
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle, Polygon
import settings, core


class Symbols:
    def __init__(self, S):
        self.S = S
        self.cache = {}
        self.by_type = {ft["name"]: ft["symbol"] for ft in S["fixture_types"]}

    def get(self, tname):
        sym_name = self.by_type.get(tname, tname)
        if sym_name not in self.cache:
            sym = settings.load_symbol(sym_name) if sym_name else None
            if sym is None:      # fallback: plain JB square
                sym = dict(name="?", w=2.4, h=2.4, jb=[0, 0, 2.4], prims=[])
            self.cache[sym_name] = sym
        return self.cache[sym_name]


def draw_sym(ax, x, y, sym, sc, lw=0.8, bw=True):
    if not sym["prims"]:
        j = sym["jb"][2] * sc
        ax.add_patch(Rectangle((x - j / 2, y - j / 2), j, j, fc="white", ec="k", lw=lw * 1.8, zorder=5))
        return
    for pr in sym["prims"]:
        pts = [(x + a * sc, y - b * sc) for a, b in pr["pts"]]
        if pr.get("fill"):
            ax.add_patch(Polygon(pts, closed=True, fc="k" if bw else pr["fill"], ec="none", zorder=4))
        if pr.get("stroke") and len(pts) >= 2:
            jbp = str(pr["stroke"]).startswith("#7f")
            ax.plot([q[0] for q in pts], [q[1] for q in pts], c="k" if bw else pr["stroke"],
                    lw=lw * (1.8 if jbp else 1), zorder=5, solid_capstyle="round")


def _row(ax, i, vals, xs, x1, y_top, rh, bold=False, fill=None, fs=9):
    y1 = y_top - i * rh
    y0 = y1 - rh
    if fill:
        ax.add_patch(Rectangle((xs[0], y0), x1 - xs[0], rh, fc=fill, ec="none"))
    ax.plot([xs[0], x1], [y0, y0], c="k", lw=0.6)
    for a, b, t in zip(xs, xs[1:], vals):
        if t is not None:
            ax.text((a + b) / 2, (y0 + y1) / 2, t, ha="center", va="center", fontsize=fs,
                    weight="bold" if bold else "normal")


def draw_cover(fig, S, built, syms):
    O = S["out"]
    types, cable = core.overall(S, built)
    names = list(types)
    ax = fig.add_axes([0.03, 0.03, 0.94, 0.85])
    ax.set_aspect("equal"); ax.axis("off"); ax.set_xlim(0, 220); ax.set_ylim(0, 140)
    fig.text(0.03, 0.95, f"{O['title']} - COVER SHEET & OVERALL MTO", fontsize=20, weight="bold")
    note = O.get("source_note") or ""
    fig.text(0.03, 0.925, f"{note}   Drawing scale 1:{S['scale']}   |   Lengths are straight-line pole to pole x {S['length_multiplier']} "
             f"(+{S['extra_per_span_m']} m per span); panel to first fixture not included", fontsize=10, color="#444")
    ncol = len(names)
    fixed = [26, 20, 18, 22]
    tw = 220 - 26 - 20 - 18 - 22 - 34 - 24
    cw = tw / max(ncol, 1)
    cx = [0]
    for w in fixed + [cw] * ncol + [34, 24]:
        cx.append(cx[-1] + w)
    hd = ["PANEL", "CIRCUIT", "POLES", "FIXTURES"] + names + ["CABLE SIZE", "LENGTH (m)"]
    RH, top = 5.6, 126
    ax.text(0, top + 2, "MTO BY CIRCUIT", fontsize=11, weight="bold", va="bottom")
    ax.plot([0, 220], [top, top], c="k", lw=1.2)
    _row(ax, 0, hd, cx, 220, top, RH, True, "#d9e2f3", 8.5)
    cs = list(built["circuits"].values())
    for n, c in enumerate(cs, 1):
        _row(ax, n, [c["key"][0], c["key"][1], str(len(c["poles"])), str(c["fixtures"])] +
             [f"{c['types'].get(t, [0, 0])[0]}/{c['types'].get(t, [0, 0])[1]}" for t in names] +
             [c["cable"], f"{c['length']:.1f}"], cx, 220, top, RH, fs=8.5)
    N = len(cs) + 1
    TL = sum(c["length"] for c in cs)
    tp = sum(len(c["poles"]) for c in cs)
    _row(ax, N, ["TOTAL", "", str(tp), str(sum(c["fixtures"] for c in cs))] +
         [f"{types[t][0]}/{types[t][1]}" for t in names] + ["", f"{TL:.1f}"], cx, 220, top, RH, True, "#f2f2f2", 8.5)
    for c in cx:
        ax.plot([c, c], [top - (N + 1) * RH, top], c="k", lw=0.6)
    ax.plot([0, 220], [top - (N + 1) * RH] * 2, c="k", lw=1.2)
    ax.text(0, top - (N + 1) * RH - 3, "Type columns show poles / fixtures (a tag with two fixtures = one pole, two fixtures).",
            fontsize=8, color="#555", va="top")
    y2 = top - (N + 1) * RH - 14
    R2 = 7.2
    ax.text(0, y2 + 2, "OVERALL MTO - FIXTURES", fontsize=11, weight="bold", va="bottom")
    c2 = [0, 16, 50, 80, 110]
    ax.plot([0, 110], [y2, y2], c="k", lw=1.2)
    _row(ax, 0, ["ITEM", "FIXTURE TYPE", "QTY (POLES)", "QTY (FIXTURES)"], c2, 110, y2, R2, True, "#d9e2f3")
    for n, t in enumerate(names, 1):
        _row(ax, n, [str(n), "          " + t, str(types[t][0]), str(types[t][1])], c2, 110, y2, R2)
        draw_sym(ax, 22, y2 - n * R2 - R2 / 2, syms.get(t), 0.42, 0.5, O["bw_symbols"])
    k = len(names) + 1
    _row(ax, k, ["", "TOTAL", str(tp), str(sum(v[1] for v in types.values()))], c2, 110, y2, R2, True, "#f2f2f2")
    _row(ax, k + 1, [str(k), "          LIGHTING JB", str(tp), "-"], c2, 110, y2, R2)
    ax.add_patch(Rectangle((19.5, y2 - (k + 1) * R2 - R2 / 2 - 1.6), 3.2, 3.2, fc="white", ec="k", lw=1.6))
    for c in c2:
        ax.plot([c, c], [y2 - (k + 2) * R2, y2], c="k", lw=0.6)
    ax.plot([0, 110], [y2 - (k + 2) * R2] * 2, c="k", lw=1.2)
    ax.text(125, y2 + 2, "OVERALL MTO - CABLE", fontsize=11, weight="bold", va="bottom")
    c3 = [125, 155, 185, 220]
    ax.plot([125, 220], [y2, y2], c="k", lw=1.2)
    _row(ax, 0, ["CABLE SIZE", "CIRCUITS", "TOTAL LENGTH (m)"], c3, 220, y2, R2, True, "#e2f0d9")
    for n, (sz, (cn, ln)) in enumerate(cable.items(), 1):
        _row(ax, n, [sz, str(cn), f"{ln:.1f}"], c3, 220, y2, R2)
    m = len(cable) + 1
    _row(ax, m, ["TOTAL", str(len(cs)), f"{TL:.1f}"], c3, 220, y2, R2, True, "#f2f2f2")
    for c in c3:
        ax.plot([c, c], [y2 - (m + 1) * R2, y2], c="k", lw=0.6)
    ax.plot([125, 220], [y2 - (m + 1) * R2] * 2, c="k", lw=1.2)


def draw_sheet(fig, S, c, syms):
    O = S["out"]
    bw = O["bw_symbols"]
    SC, PER, DX, DY = O["symbol_scale"], int(O["per_row"]), O["dx"], O["dy"]
    GRN, LCOL = O["line_color"], O["length_color"]
    k, v, segs = c["key"], c["poles"], c["segs"]
    rows = (len(v) + PER - 1) // PER
    ax = fig.add_axes([0.02, 0.23, 0.96, 0.65])
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_xlim(-100, PER * DX - 18); ax.set_ylim(-(rows - 1) * DY - 62, 40)
    fig.text(0.02, 0.95, f"{O['title']} - PANEL {k[0]} - CIRCUIT {k[1]}", fontsize=18, weight="bold")
    fig.text(0.02, 0.925, f"{len(v)} poles / {c['fixtures']} fixtures.  JB tag = fixture tag + '{S['jb_suffix']}'.  Cable tag e.g. {core.cable_tag(S, c, 1)}", fontsize=10, color="#444")
    fig.text(0.02, 0.885, f"Length between fixtures measured from the drawing at 1:{S['scale']} (straight line between symbols). "
             f"Total pole-to-pole length: {c['length']:.1f} m", fontsize=10, color=LCOL)
    for i, ft in enumerate(S["fixture_types"][:6]):
        a2 = fig.add_axes([0.52 + i * 0.075, 0.90, 0.07, 0.07]); a2.set_aspect("equal"); a2.axis("off")
        a2.set_xlim(-30, 30); a2.set_ylim(-40, 22)
        draw_sym(a2, 0, 4, syms.get(ft["name"]), 3.0, 0.8, bw)
        a2.text(0, -26, ft["name"], ha="center", va="top", fontsize=9, weight="bold")
    px, py = -72, 0
    ax.add_patch(Rectangle((px - 14, py - 9), 28, 18, fc="#e8d5f0", ec="#800080", lw=1.5, zorder=3))
    ax.text(px, py, f"{k[0]}\nCCT {k[1]}", ha="center", va="center", fontsize=7.5, weight="bold", zorder=4)
    cur = None
    for i, p in enumerate(v):
        r, col = divmod(i, PER)
        x = col * DX if r % 2 == 0 else (PER - 1 - col) * DX
        y = -r * DY
        sym = syms.get(p["ld"])
        jcx, jcy, jsz = sym["jb"]
        jh = jsz * SC / 2
        hh = sym["h"] * SC / 2
        ya, xa = y + jcy * SC, x - jcx * SC
        if i == 0:
            pts = [(px + 14, py), (x - jh, y)] if abs(py - y) < 1 else [(px + 14, py), (px + 14, y), (x - jh, y)]
        else:
            px2, py2, jh0 = cur
            if abs(py2 - y) < 1:
                pts = [(px2 + (jh0 if x > px2 else -jh0), y), (x + (-jh if x > px2 else jh), y)]
            else:
                out = 1 if (r - 1) % 2 == 0 else -1
                pts = [(px2 + out * jh0, py2), (px2 + out * 44, py2), (px2 + out * 44, y), (x + out * jh, y)]
        ax.plot([q[0] for q in pts], [q[1] for q in pts], c=GRN, lw=1.4, zorder=1)
        ax.annotate("", xy=pts[-1], xytext=pts[-2], arrowprops=dict(arrowstyle="-|>", color=GRN, lw=1.4), zorder=2)
        ctag = core.cable_tag(S, c, i + 1)
        horiz = abs(pts[0][1] - pts[-1][1]) < 1
        mx = (pts[0][0] + pts[-1][0]) / 2
        if i == 0:
            if O["show_cable_tag"]:
                ax.text(mx, y + 2, ctag, ha="center", va="bottom", fontsize=6.5, weight="bold", zorder=6)
        else:
            L = segs[i - 1]
            if horiz:
                if O["show_cable_tag"]:
                    ax.text(mx, y + 2, ctag, ha="center", va="bottom", fontsize=6.5, weight="bold", zorder=6)
                ax.text(mx, y - 2, f"{L:.1f} m", ha="center", va="top", fontsize=7.5, weight="bold", color=LCOL, zorder=6)
            else:
                ha = "left" if out > 0 else "right"
                my = (pts[1][1] + pts[2][1]) / 2
                if O["show_cable_tag"]:
                    ax.text(pts[1][0] + out * 3, my + 3, ctag, ha=ha, va="bottom", fontsize=6.5, weight="bold", zorder=6)
                ax.text(pts[1][0] + out * 3, my + 1, f"{L:.1f} m", ha=ha, va="top", fontsize=7.5, weight="bold", color=LCOL, zorder=6)
        draw_sym(ax, xa, ya, sym, SC, 0.8, bw)
        cur = (x, y, jh)
        ty = ya - hh - 3
        ax.text(x, ty, f"{i + 1}  {p['ld'] or '?'}", ha="center", va="top", fontsize=6.5, color="#555")
        ax.text(x, ty - 7, p["new"], ha="center", va="top", fontsize=7, weight="bold", color=O["tag_text"],
                bbox=dict(boxstyle="square,pad=0.3", fc=O["tag_fill"], ec=O["tag_edge"], lw=1.2))
        yy = ty - 17
        if O["show_jb_tag"]:
            ax.text(x, yy, S["jb_label"] + p["new"] + S["jb_suffix"], ha="center", va="top", fontsize=6.5, weight="bold",
                    bbox=dict(boxstyle="square,pad=0.25", fc="white", ec="k", lw=1.0))
            yy -= 9
        if O["show_old_tag"] and p["old"]:
            ax.text(x, yy, "old: " + p["old"], ha="center", va="top", fontsize=5, color="#555")
    # MTO
    names = [t for t, (a, b) in c["types"].items() if a]
    ta = fig.add_axes([0.02, 0.015, 0.62, 0.205]); ta.set_aspect("equal"); ta.axis("off")
    RH = 5.2
    ta.set_xlim(0, 150); ta.set_ylim(0, RH * 8.4)
    cols = [0, 14, 44, 80, 115, 150]
    top = RH * 7.2
    ta.text(0, top + 1, f"MTO - PANEL {k[0]} - CIRCUIT {k[1]}", fontsize=10, weight="bold", va="bottom")
    ta.plot([0, 150], [top, top], c="k", lw=1.2)
    _row(ta, 0, ["ITEM", None, "FIXTURE TYPE", "QTY (POLES)", "QTY (FIXTURES)"], cols, 150, top, RH, True, "#d9e2f3", 8.5)
    for n, t in enumerate(names, 1):
        _row(ta, n, [str(n), None, t, str(c["types"][t][0]), str(c["types"][t][1])], cols, 150, top, RH, fs=8.5)
        draw_sym(ta, 29, top - n * RH - RH / 2, syms.get(t), 0.42, 0.5, bw)
    n = len(names)
    _row(ta, n + 1, [None, None, "TOTAL", str(len(v)), str(c["fixtures"])], cols, 150, top, RH, True, "#f2f2f2", 8.5)
    _row(ta, n + 2, [None, None, "CABLE SIZE: " + c["cable"], "TOTAL LENGTH", f"{c['length']:.1f} m"], cols, 150, top, RH, True, "#e2f0d9", 8.5)
    for cc in cols:
        ta.plot([cc, cc], [top - (n + 3) * RH, top], c="k", lw=0.6)
    ta.plot([0, 150], [top - (n + 3) * RH] * 2, c="k", lw=1.2)
    fig.text(0.67, 0.19, f"CABLE (from drawing, 1:{S['scale']})", fontsize=10, weight="bold")
    fig.text(0.67, 0.16, f"Cable size: {c['cable']}   Pole-to-pole length: {c['length']:.1f} m", fontsize=9.5)
    fig.text(0.67, 0.135, f"Number of spans: {len(segs)}" + (f"   (longest {max(segs):.1f} m)" if segs else ""), fontsize=9.5)
    fig.text(0.67, 0.11, f"Lighting JB: {len(v)} nos", fontsize=9.5)
    fig.text(0.67, 0.085, "Panel to first fixture length not included.", fontsize=8.5, color="#666")


def new_fig(S):
    import settings as _st
    return plt.figure(figsize=_st.page_size(S))


def sheet_figure(S, built, key, syms):
    if built.get("source") == "excel":
        import render_tree
        return render_tree.sheet_figure_excel(S, built, key, syms)
    fig = new_fig(S)
    if key is None:
        draw_cover(fig, S, built, syms)
    else:
        draw_sheet(fig, S, built["circuits"][key], syms)
    return fig


def export_pdf(path, S, built):
    if built.get("source") == "excel":
        import render_tree
        return render_tree.export_pdf_excel(path, S, built)
    syms = Symbols(S)
    with PdfPages(path) as pdf:
        for key in [None] + list(built["circuits"]):
            fig = sheet_figure(S, built, key, syms)
            pdf.savefig(fig)
            plt.close(fig)
