"""Looping diagrams for the Excel input: branching circuits (FROM links), lengths from the Excel.
Works on any paper (A4..A0, Letter, Tabloid), portrait or landscape, with horizontal (rows) or vertical (columns) flow."""
import collections, math, textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle
import core, render, settings as st
from render import draw_sym, _row


def layout(poles):
    kids = collections.defaultdict(list)
    roots = []
    for p in poles:
        (roots if p["parent"] < 0 else kids[p["parent"]]).append(p["idx"])
    size = {}

    def sz(i):
        size[i] = 1 + sum(sz(j) for j in kids[i])
        return size[i]
    for r in roots:
        sz(r)
    order = []

    def dfs(i):
        order.append(i)
        for j in sorted(kids[i], key=lambda j: (-size[j], j)):
            dfs(j)
    for r in roots:
        dfs(r)
    return order


# ---- sizes below are in INCHES at A3 (multiplied by K = font/size factor of the paper)
STACK = 0.66      # height of the text stack under a symbol (type line + tag + JB tag)
ROWGAP = 0.47     # free band between two rows (cable lanes run here)
GAP3 = 0.06       # symbol -> first text line
TAG_OFF, JB_OFF = 0.16, 0.39
LM = 2.92         # left margin (panel box lives here)
TOPM = 0.27       # head-room above the highest symbol


class Geo:
    """Page geometry for any paper size / orientation."""
    def __init__(self, fig):
        self.W, self.H = fig.get_size_inches()
        self.kg = min(self.W, self.H) / 11.69          # sizes scale with the short side (A3 = 1)
        self.K = max(0.8, self.kg)                     # fonts never smaller than 80 %
        self.narrow = (self.W / self.kg) < 15.5        # portrait or small page: legend goes below the header
        self.top_in = (1.41 + (0.85 if self.narrow else 0.0)) * self.kg
        self.bot_in = 2.51 * self.kg
        self.wa = self.W * 0.96
        self.ha = self.H - self.top_in - self.bot_in
        self.ax = [0.02, self.bot_in / self.H, 0.96, self.ha / self.H]

    def fy(self, d):                                   # figure y-fraction for `d` inches (A3 scale) below the top edge
        return (self.H - d * self.kg) / self.H


def _vert(S):
    return str(S["out"].get("layout_dir", "horizontal")).lower().startswith("v")


def _text_w_in(fig, S, c, syms, K):
    """Widest label in inches (measured with the real renderer)."""
    r = fig.canvas.get_renderer()
    w = 0.0
    for p in c["poles"]:
        for txt, fs in ((p["tag"], 7), (S["jb_label"] + p["tag"] + S["jb_suffix"], 6)):
            t = fig.text(0, 0, txt, fontsize=fs * K, weight="bold")
            w = max(w, t.get_window_extent(r).width / fig.dpi)
            t.remove()
    return w + 0.12 * K      # box padding


def _ext(S, c, syms):
    """symbol extent above / below the JB point, in drawing units"""
    SC = S["out"]["symbol_scale"]
    top = dep = 0.0
    for p in c["poles"]:
        sym = syms.get(p["ld"])
        jcx, jcy, jsz = sym["jb"]
        top = max(top, (jcy + sym["h"] / 2) * SC)
        dep = max(dep, (sym["h"] / 2 - jcy) * SC)
    return top, dep


def _per_list(S, vert):
    fixed = int(S["out"].get("tree_per_row", 0) or 0)
    return [fixed] if fixed > 0 else list(range(3, 16 if vert else 13))


def _wext(S, c, syms):
    """symbol extent left / right of the JB point (drawing units)"""
    SC = S["out"]["symbol_scale"]
    le = re_ = 0.0
    for p in c["poles"]:
        sym = syms.get(p["ld"])
        jcx = sym["jb"][0]
        le = max(le, sym["w"] * SC / 2 + jcx * SC)
        re_ = max(re_, sym["w"] * SC / 2 - jcx * SC)
    return le, re_


VT_TOP, VT_BOT, VT_TXT, VT_GAP = 0.55, 0.5, 0.6, 0.15     # vertical layout: lane bands, text block height, row gap (inches at A3)


def _dxc(S, c, syms, tw, K, T):
    le, re_ = _wext(S, c, syms)
    return (le + re_) * T + tw + 1.43 * K


def _cands(S, c, syms, G, tw):
    """every poles-per-row (or per-column) option that fits the page, with the largest symbol size T (page inches per drawing unit)"""
    K = G.K
    vert = _vert(S)
    top, dep = _ext(S, c, syms)
    n = len(c["poles"])
    out = []
    for per in _per_list(S, vert):
        pe = min(per, n)
        if vert:
            R, cols = pe, math.ceil(n / per)
            s = top + dep
            T = (G.ha - (VT_TOP + VT_BOT) * K - (R - 1) * VT_GAP * K) / (R * s)
            if T * s < VT_TXT * K:
                T = (G.ha - (VT_TOP + VT_BOT) * K - (R - 1) * (VT_TXT + VT_GAP) * K) / s
            if T <= 0:
                continue
            le, re_ = _wext(S, c, syms)
            D = _dxc(S, c, syms, tw, K, T)
            xs = LM * K + (cols - 1) * D + re_ * T + 0.38 * K + tw
        else:
            cc = (GAP3 + STACK + ROWGAP) * K
            D = max(1.5 * K, tw + 0.30 * K)
            R, cols = math.ceil(n / per), pe
            xs = LM * K + (pe - 1) * D + D / 2 + 0.78 * K
            T = ((G.ha - TOPM * K) / R - cc) / (top + dep)
            if T <= 0:
                continue
        if xs > G.wa + 1e-9:
            continue
        out.append(dict(per=per, R=R, cols=cols, T=T, D=D))
    return out


def _pick(cs, T, vert):
    fits = [x for x in cs if x["T"] >= T - 1e-9]
    if not fits:
        return None
    return min(fits, key=lambda x: ((x["cols"] if vert else x["R"]), x["per"]))


def common_scale(S, built, syms):
    """ONE symbol size for every sheet: the largest size at which the biggest circuit still fits the paper
    (limited by Settings -> Output -> symbol size when that is > 0).  Cached on the built data."""
    O = S["out"]
    cap = float(O.get("symbol_inches_per_unit", 0.0) or 0.0)
    W, H = st.page_size(S)
    vert = _vert(S)
    key = (cap, tuple(_per_list(S, vert)), O["symbol_scale"], round(W, 2), round(H, 2), vert, S["jb_label"] + S["jb_suffix"])
    if built.get("_T_key") == key:
        return built["_T"]
    fig = plt.figure(figsize=(W, H))
    G = Geo(fig)
    worst = None
    for c in built["circuits"].values():
        tw = _text_w_in(fig, S, c, syms, G.K)
        cs = _cands(S, c, syms, G, tw)
        best = max((x["T"] for x in cs), default=0.003)
        worst = best if worst is None else min(worst, best)
    plt.close(fig)
    worst = worst or 0.003
    T = min(worst, cap) if cap > 0 else worst
    built["_T"], built["_T_key"], built["_T_fit"] = T, key, worst
    note = None
    if cap > 0 and cap > worst + 1e-9:
        note = (f"Symbol size {cap:g} in/unit does not fit on {O.get('paper')} {O.get('orientation')} "
                f"without overlapping - {worst:.4f} in/unit (largest that fits every circuit) was used.")
    built["checks"] = [x for x in built["checks"] if not x.startswith("Symbol size ")]
    if note:
        built["checks"].append(note)
    built["layout_note"] = note
    return T


def _wrap(text, width_in, fs):
    return "\n".join(textwrap.wrap(text, max(10, int(width_in * 72 / (fs * 0.56)))))


def draw_tree_sheet(fig, S, c, syms, T=None):
    O = S["out"]
    bw = O["bw_symbols"]
    SC = O["symbol_scale"]
    GRN, LCOL = O["line_color"], O["length_color"]
    G = Geo(fig)
    K = G.K
    vert = _vert(S)
    poles = c["poles"]
    order = layout(poles)
    pos = {i: k for k, i in enumerate(order)}
    n = len(order)
    tw = _text_w_in(fig, S, c, syms, K)
    cs = _cands(S, c, syms, G, tw)
    if T is None:
        T = max((x["T"] for x in cs), default=0.003)
        cap = float(O.get("symbol_inches_per_unit", 0.0) or 0.0)
        T = min(T, cap) if cap > 0 else T
    pick = _pick(cs, T, vert)
    if pick is None:          # page too small for this circuit - least bad option
        pick = dict(per=3, D=_dxc(S, c, syms, tw, K, T) if vert else max(1.5 * K, tw + 0.30 * K))
    PER = pick["per"]
    Din = _dxc(S, c, syms, tw, K, T) if vert else pick["D"]

    def I(inches):            # inches (A3 size, scaled by K) -> drawing units
        return inches * K / T
    top, dep = _ext(S, c, syms)
    TOP = top
    DXu = Din / T
    if vert:
        LE, RE = _wext(S, c, syms)
        DY = max(top + dep, I(VT_TXT)) + I(VT_GAP)
    else:
        DY = top + dep + I(GAP3 + STACK + ROWGAP)
    ax = fig.add_axes(G.ax)
    ax.set_aspect("equal"); ax.axis("off")
    x0 = -I(LM); ytop = TOP + I(VT_TOP if vert else TOPM)
    ax.set_xlim(x0, x0 + G.wa / T); ax.set_ylim(ytop - G.ha / T, ytop)      # exact common scale: T inches per drawing unit
    c["_T"] = T
    ax.apply_aspect()
    # ---- header
    kind = c["kind"].title()
    fig.text(0.02, G.fy(0.58), f"{O['title']} - {kind.upper()} PANEL {c['key'][0]} - CIRCUIT {c['key'][1]}", fontsize=16 * K, weight="bold")
    area = c["area"].split("|")[0].split(":", 1)[-1].strip()
    fig.text(0.02, G.fy(0.88), f"Area: {area}   |   {len(poles)} poles / {c['fixtures']} fixtures", fontsize=9.5 * K, color="#444")
    fig.text(0.02, G.fy(1.09), f"Source: Excel sheet '{c['sheet']}'", fontsize=8 * K, color="#777")
    hw_in = (0.58 if not G.narrow else 0.96) * G.W
    fig.text(0.02, G.fy(1.34), _wrap(f"Cable lengths as per Excel (m). Total cable length: {c['length']:.0f} m.  JB tag = fixture tag + '{S['jb_suffix']}'.  "
                                     f"Cable tag e.g. {core.cable_tag(S, c, 1)}", hw_in, 10 * K), fontsize=10 * K, color=LCOL, va="center")
    nft = min(6, len(S["fixture_types"]))
    if nft:
        lx0 = (0.62 * G.W) if not G.narrow else 0.02 * G.W
        step = min(1.49 * G.kg, (G.W - 0.1 - lx0) / nft)
        ytop_in = (0.35 if not G.narrow else 1.45) * G.kg
        lh = 0.82 * G.kg
        for i, ft in enumerate(S["fixture_types"][:6]):
            a2 = fig.add_axes([(lx0 + i * step) / G.W, (G.H - ytop_in - lh) / G.H, step * 0.9 / G.W, lh / G.H])
            a2.set_aspect("equal"); a2.axis("off")
            a2.set_xlim(-30, 30); a2.set_ylim(-40, 22)
            draw_sym(a2, 0, 4, syms.get(ft["name"]), 3.0, 0.8, bw)
            a2.text(0, -26, ft["name"], ha="center", va="top", fontsize=9 * K, weight="bold")
    # ---- panel box
    px, py = -I(2.18), 0.0
    hwp, hhp = I(0.35), I(0.21)
    ax.add_patch(Rectangle((px - hwp, py - hhp), 2 * hwp, 2 * hhp, fc="#e8d5f0", ec="#800080", lw=1.5, zorder=3))
    ax.text(px, py, f"{c['key'][0]}\nCCT {c['key'][1]}", ha="center", va="center", fontsize=7.5 * K, weight="bold", zorder=4)
    # ---- nodes
    info, rowdepth = {}, collections.defaultdict(float)
    for i in order:
        p = poles[i]
        k = pos[i]
        if vert:
            cl, r0 = divmod(k, PER)
            r = r0 if cl % 2 == 0 else PER - 1 - r0
            x, y = cl * DXu, -r * DY
        else:
            r, col = divmod(k, PER)
            cl = col if r % 2 == 0 else PER - 1 - col
            x, y = cl * DXu, -r * DY
        sym = syms.get(p["ld"])
        jcx, jcy, jsz = sym["jb"]
        info[i] = dict(x=x, y=y, row=r, col=cl, jh=jsz * SC / 2, sym=sym, ya=y + jcy * SC, xa=x - jcx * SC, hh=sym["h"] * SC / 2,
                       hw=sym["w"] * SC / 2, in_right=False, stub=False, stub_arrow=False)
        if vert:
            info[i]["sx"] = x - LE - I(0.2)           # spine (cable run) on the left of the symbol
            info[i]["tx"] = x + RE + I(0.08)          # text block on the right of the symbol
        rowdepth[r] = max(rowdepth[r], (sym["h"] / 2 - jcy) * SC + I(GAP3 + STACK))
    for i in order:
        p = poles[i]
        C = info[i]
        x, sym = C["x"], C["sym"]
        draw_sym(ax, C["xa"], C["ya"], sym, SC, 0.8, bw)
        ty = C["ya"] - C["hh"] - I(GAP3)
        phs = "+".join(sorted({"L" + r["tag"].split("L")[-1][0] if "L" in r["tag"] else "" for r in p["rows"]}))
        if vert:
            tx, t0 = C["tx"], C["y"] + I(VT_TXT / 2)
            ax.text(tx, t0, f"{pos[i] + 1}  {p['ld'] or p['type'] or '?'}  {phs}  {p['watt']:g} W", ha="left", va="top", fontsize=6 * K, color="#555")
            ax.text(tx, t0 - I(TAG_OFF), p["tag"], ha="left", va="top", fontsize=7 * K, weight="bold", color=O["tag_text"],
                    bbox=dict(boxstyle="square,pad=0.3", fc=O["tag_fill"], ec=O["tag_edge"], lw=1.2))
            if O["show_jb_tag"]:
                ax.text(tx, t0 - I(JB_OFF), S["jb_label"] + p["tag"] + S["jb_suffix"], ha="left", va="top", fontsize=6 * K, weight="bold",
                        bbox=dict(boxstyle="square,pad=0.25", fc="white", ec="k", lw=1.0))
            continue
        ax.text(x, ty, f"{pos[i] + 1}  {p['ld'] or p['type'] or '?'}  {phs}  {p['watt']:g} W", ha="center", va="top", fontsize=6 * K, color="#555")
        ax.text(x, ty - I(TAG_OFF), p["tag"], ha="center", va="top", fontsize=7 * K, weight="bold", color=O["tag_text"],
                bbox=dict(boxstyle="square,pad=0.3", fc=O["tag_fill"], ec=O["tag_edge"], lw=1.2))
        if O["show_jb_tag"]:
            ax.text(x, ty - I(JB_OFF), S["jb_label"] + p["tag"] + S["jb_suffix"], ha="center", va="top", fontsize=6 * K, weight="bold",
                    bbox=dict(boxstyle="square,pad=0.25", fc="white", ec="k", lw=1.0))
    lane_below = lambda r: -r * DY - rowdepth[r] - I(0.18)
    rend = fig.canvas.get_renderer()
    inv = ax.transData.inverted()

    def rect_of(t, pad=0.0):
        bb = t.get_window_extent(rend)
        (xa, ya), (xb, yb) = inv.transform((bb.x0, bb.y0)), inv.transform((bb.x1, bb.y1))
        return (xa - pad, ya - pad, xb + pad, yb + pad)
    blockers = [rect_of(t, 0.5) for t in ax.texts if t.get_text().strip()]
    for i in order:
        C = info[i]
        blockers.append((C["xa"] - C["hw"], C["ya"] - C["hh"], C["xa"] + C["hw"], C["ya"] + C["hh"]))
    blockers.append((px - hwp, py - hhp, px + hwp, py + hhp))
    # ---- routes (computed first so labels can keep clear of every line)
    alloc = collections.defaultdict(int)

    def lane_no(key):
        m = alloc[key]; alloc[key] += 1
        return m

    def side_track(key, step):
        m = alloc[key]; alloc[key] += 1
        return step * ((m // 2) + 1) * (-1 if m % 2 == 0 else 1)

    def track(key, step):
        m = alloc[key]; alloc[key] += 1
        return step * ((m + 1) // 2) * (1 if m % 2 else -1) if m else 0

    def one_side(key, step, sign):
        m = alloc[key]; alloc[key] += 1
        return sign * step * m
    links = []
    for i in order:
        p = poles[i]
        nn = pos[i] + 1
        C = info[i]
        par = p["parent"]
        x2, y2, jh2 = C["x"], C["y"], C["jh"]
        if par < 0:
            x1, y1, jh1, r1, hw1 = px, py, hwp, 0, hwp
            P = None
        else:
            P = info[par]
            x1, y1, jh1, r1, hw1 = P["x"], P["y"], P["jh"], P["row"], P["hw"]
        adjacent = (par >= 0 and pos[par] == pos[i] - 1) or (par < 0 and pos[i] == 0)
        if vert:
            sx2 = C["sx"]
            Rn = max(info[j]["row"] for j in order) + 1
            top_lane = lambda: TOP + I(0.2) + I(0.09) * lane_no(("lt",))
            bot_lane = lambda: -(Rn - 1) * DY - dep - I(0.2) - I(0.09) * lane_no(("lb",))
            if par < 0:
                pts = [(px + hwp, py), (sx2, y2)]
                C["stub"] = C["stub_arrow"] = True
                kindl = ("direct", px + hwp, sx2, y2)
            elif adjacent and C["col"] == P["col"]:
                pts = [(sx2, y1), (sx2, y2)]
                C["stub"] = C["stub_arrow"] = True
                P["stub"] = True
                kindl = ("spine", sx2, y1, y2)
            elif adjacent:                                   # snake turn to the next column: via the lane below / above
                yl = bot_lane() if C["row"] >= (Rn - 1) / 2 else top_lane()
                pts = [(P["sx"], y1), (P["sx"], yl), (sx2, yl), (sx2, y2)]
                C["stub"] = C["stub_arrow"] = True
                P["stub"] = True
                kindl = ("lane", P["sx"], sx2, yl)
            else:                                            # branch: leaves the parent's tap to the left, runs in a lane
                sx1 = P["sx"]
                xc1 = sx1 - I(0.14) - one_side(("c", round(sx1)), I(0.1), 1)
                xc2 = sx2 - I(0.14) - one_side(("c", round(sx2)), I(0.1), 1)
                yl = bot_lane() if r1 >= (Rn - 1) / 2 else top_lane()
                if poles[par]["parent"] < 0 and not alloc[("p", par)]:
                    alloc[("p", par)] += 1               # the panel feed already comes in from the left at this height
                ys = y1 + side_track(("p", par), I(0.07)) if alloc[("p", par)] else y1
                if not alloc[("p", par)]:
                    alloc[("p", par)] += 1
                pts = [(sx1, ys), (xc1, ys), (xc1, yl), (xc2, yl), (xc2, y2), (sx2, y2)]
                C["stub"] = C["stub_arrow"] = True
                P["stub"] = True
                kindl = ("lane", xc1, xc2, yl)
        else:
            same = C["row"] == r1
            if adjacent and same:
                s1 = 1 if x2 > x1 else -1
                pts = [(x1 + s1 * jh1, y1), (x2 - s1 * jh2, y2)]
                kindl = ("direct", min(x1 + s1 * hw1, x2 - s1 * C["hw"]), max(x1 + s1 * hw1, x2 - s1 * C["hw"]), y2)
            elif adjacent:
                out = 1 if (C["row"] - 1) % 2 == 0 else -1
                gx = x1 + out * (DXu / 2 + I(0.43))
                pts = [(x1 + out * jh1, y1), (gx, y1), (gx, y2), (x2 + out * jh2, y2)]
                kindl = ("wrap", gx, out, (y1 + y2) / 2)
            else:
                rd = 1 if C["row"] % 2 == 0 else -1
                gap = DXu / 2
                xb2 = x2 - rd * gap
                s1 = 1 if xb2 >= x1 else -1
                base_lane = lane_below(r1) if same else lane_below(C["row"] - 1)
                xb1 = (x1 + s1 * jh1 + I(0.5)) if par < 0 else (x1 + s1 * gap)
                xg1 = xb1 + track(("g", round(xb1)), I(0.1))
                xg2 = xb2 + track(("g", round(xb2)), I(0.1))
                ylane = base_lane - I(0.09) * lane_no(("l", round(base_lane)))
                ys = y1 + side_track(("p", par, s1), I(0.06))
                ex = x2 - rd * jh2
                pts = [(x1 + s1 * jh1, ys), (xg1, ys), (xg1, ylane), (xg2, ylane), (xg2, y2), (ex, y2)]
                kindl = ("lane", xg1, xg2, ylane)
        links.append((i, nn, pts, kindl))
    # taps of the vertical layout (spine <-> JB), drawn once
    stubs = []
    for i in order:
        C = info[i]
        if vert and C["stub"]:
            if C["stub_arrow"]:
                stubs.append(([(C["sx"], C["y"]), (C["x"] - C["jh"], C["y"])], True))
            else:
                stubs.append(([(C["x"] - C["jh"], C["y"]), (C["sx"], C["y"])], False))
    segs = [(li, p, q) for li, (_, _, pts, _) in enumerate(links) for p, q in zip(pts, pts[1:])]
    segs += [(-1, pts[0], pts[1]) for pts, _ in stubs]
    c["_routes"] = [l[2] for l in links] + [s[0] for s in stubs]
    placed = []

    XL0, XL1 = ax.get_xlim()
    YL0, YL1 = ax.get_ylim()

    def hits(r, own=None):
        xa, ya, xb, yb = r
        if xa < XL0 or xb > XL1 or ya < YL0 or yb > YL1:       # keep every label on the paper
            return True
        for b0 in blockers + placed:
            if xa < b0[2] and b0[0] < xb and ya < b0[3] and b0[1] < yb:
                return True
        for li, p, q in segs:
            if abs(p[0] - q[0]) < 1e-6:
                if xa - 0.3 < p[0] < xb + 0.3 and not (max(p[1], q[1]) < ya or min(p[1], q[1]) > yb):
                    return True
            elif abs(p[1] - q[1]) < 1e-6:
                if ya - 0.3 < p[1] < yb + 0.3 and not (max(p[0], q[0]) < xa or min(p[0], q[0]) > xb):
                    return True
        return False

    def place(specs, xs, ys_shift=(0,), final=True):
        """specs: list of (text, y, dy, va, fontsize, color); try candidate x / y shifts until nothing is touched"""
        for dyv in ys_shift:
            for cx in xs:
                ts = [ax.text(cx[0] if isinstance(cx, tuple) else cx, base + dy + dyv, txt, ha=cx[1] if isinstance(cx, tuple) else "center", va=va,
                              fontsize=fs, weight="bold", color=col, zorder=7)
                      for (txt, base, dy, va, fs, col) in specs]
                rs = [rect_of(t, 0.6) for t in ts]
                if not any(hits(r) for r in rs):
                    placed.extend(rs)
                    return True
                for t in ts:
                    t.remove()
        if not final:
            return False
        cx = xs[0]
        for (txt, base, dy, va, fs, col) in specs:
            t = ax.text(cx[0] if isinstance(cx, tuple) else cx, base + dy, txt, ha=cx[1] if isinstance(cx, tuple) else "center", va=va, fontsize=fs,
                        weight="bold", color=col, zorder=7, bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.95))
            placed.append(rect_of(t, 0.6))
        return False

    def two_line(t):
        return t.rsplit("-", 1)[0] + "-\n" + t.rsplit("-", 1)[1] if "-" in t else t
    f65, f75 = 6.5 * K, 7.5 * K
    for li, (i, nn, pts, kl) in enumerate(links):
        ctag = core.cable_tag(S, c, nn)
        L = poles[i]["length"]
        ltxt = f"{L:g} m" if L is not None else "? m"
        sp = []
        if kl[0] == "direct":
            _, gx0, gx1, y = kl
            mid, w = (gx0 + gx1) / 2, gx1 - gx0
            xsl = [mid, mid - 0.22 * w, mid + 0.22 * w, mid - 0.35 * w, mid + 0.35 * w]
            sh = I(0.18)
            if O["show_cable_tag"]:
                if not place([(ctag, y, I(0.05), "bottom", f65, "k")], xsl, ys_shift=(0, sh, 2 * sh, 3 * sh), final=False):
                    place([(two_line(ctag), y, I(0.05), "bottom", f65, "k")], xsl, ys_shift=(0, sh, 2 * sh, 3 * sh))
            place([(ltxt, y, -I(0.05), "top", f75, LCOL)], xsl, ys_shift=(0, -sh, -2 * sh, 0.78 * sh, 1.2 * sh, 1.7 * sh, 2.1 * sh))
        elif kl[0] == "wrap":
            _, gx, out, my = kl
            ha_out, ha_in = ("left", "right") if out > 0 else ("right", "left")
            if O["show_cable_tag"]:
                sp.append((ctag, my, I(0.05), "bottom", f65, "k"))
            sp.append((ltxt, my, I(0.01), "top", f75, LCOL))
            sh = I(0.23)
            place(sp, [(gx + out * I(0.06), ha_out), (gx - out * I(0.06), ha_in)], ys_shift=(0, sh / 2, -sh / 2, sh, -sh))
        elif kl[0] == "spine":
            _, sx, ya_, yb_ = kl
            my = (ya_ + yb_) / 2
            if O["show_cable_tag"]:
                sp.append((ctag, my, I(0.04), "bottom", f65, "k"))
            sp.append((ltxt, my, -I(0.01), "top", f75, LCOL))
            sh = I(0.14)
            half = abs(ya_ - yb_) / 2
            shifts = [0] + [v * k_ for k_ in range(1, 8) for v in (sh, -sh) if abs(v * k_) < half]
            xr = [(sx - I(0.06), "right"), (sx - I(0.32), "right"), (sx - I(0.6), "right")]
            if not place(sp, xr, ys_shift=shifts, final=False):
                one = [((ctag + "  " if O["show_cable_tag"] else "") + ltxt, my, 0, "center", f65, LCOL)]
                place(one, xr, ys_shift=shifts + [I(0.5), -I(0.5)])
        else:
            _, xg1, xg2, ylane = kl
            txt = (ctag + "  " if O["show_cable_tag"] else "") + ltxt
            sp = [(txt, ylane, -I(0.04), "top", f65, LCOL)]
            lo, hi = min(xg1, xg2), max(xg1, xg2)
            xsl = [xg2, (xg1 + xg2) / 2, xg1]
            for d_ in (0.78, 1.1, 1.45, 1.9):
                xsl += [xg2 + I(d_), xg2 - I(d_), xg1 + I(d_), xg1 - I(d_)]
            if vert:
                xsl += [lo + (hi - lo) * f for f in (0.25, 0.75, 0.1, 0.9)]
            sh = I(0.12)
            if not place(sp, xsl, ys_shift=(0, -sh / 2, -sh), final=False):
                sp2 = [(two_line(ctag) + "\n" + ltxt if O["show_cable_tag"] else ltxt, ylane, -I(0.04), "top", f65, LCOL)]
                place(sp2, xsl, ys_shift=(0, -sh / 3, -2 * sh / 3, -sh, -4 * sh / 3, I(0.23), I(0.39)))
    for i, nn, pts, kl in links:
        ax.plot([q[0] for q in pts], [q[1] for q in pts], c=GRN, lw=1.4, zorder=1)
        if kl[0] not in ("spine",) and not vert:
            ax.annotate("", xy=pts[-1], xytext=pts[-2], arrowprops=dict(arrowstyle="-|>", color=GRN, lw=1.4), zorder=2)
    for pts, arrow in stubs:
        ax.plot([q[0] for q in pts], [q[1] for q in pts], c=GRN, lw=1.4, zorder=1)
        if arrow:
            ax.annotate("", xy=pts[-1], xytext=pts[0], arrowprops=dict(arrowstyle="-|>", color=GRN, lw=1.4), zorder=2)
    c["_ax"] = ax
    c["_symbox"] = [(info[i]["xa"] - info[i]["hw"], info[i]["ya"] - info[i]["hh"], info[i]["xa"] + info[i]["hw"], info[i]["ya"] + info[i]["hh"]) for i in order]
    c["_layout"] = dict(per=PER, vert=vert, T=T)
    _mto_block(fig, S, c, syms, G)


def _mto_block(fig, S, c, syms, G):
    O = S["out"]
    bw = O["bw_symbols"]
    poles = c["poles"]
    names = [t for t, (a, b) in c["types"].items() if a]
    W, H, kg, K = G.W, G.H, G.kg, G.K
    wf = 0.62 if not G.narrow else 0.58
    ta = fig.add_axes([0.02, 0.175 * kg / H, wf, 2.4 * kg / H]); ta.set_aspect("equal"); ta.axis("off")
    RH = 5.2
    ta.set_xlim(0, 150); ta.set_ylim(0, RH * 8.4)
    ms = min(wf * W / 150, 2.4 * kg / (RH * 8.4)) / (2.4 / (RH * 8.4))      # table scale vs A3
    f85 = 8.5 * ms
    cols = [0, 14, 44, 80, 115, 150]
    top = RH * 7.2
    ta.text(0, top + 1, f"MTO - PANEL {c['key'][0]} - CIRCUIT {c['key'][1]}", fontsize=10 * ms, weight="bold", va="bottom")
    ta.plot([0, 150], [top, top], c="k", lw=1.2)
    _row(ta, 0, ["ITEM", None, "FIXTURE TYPE", "QTY (POLES)", "QTY (FIXTURES)"], cols, 150, top, RH, True, "#d9e2f3", f85)
    for n, t in enumerate(names, 1):
        _row(ta, n, [str(n), None, t, str(c["types"][t][0]), str(c["types"][t][1])], cols, 150, top, RH, fs=f85)
        draw_sym(ta, 29, top - n * RH - RH / 2, syms.get(t), 0.42, 0.5, bw)
    n = len(names)
    _row(ta, n + 1, [None, None, "TOTAL", str(len(poles)), str(c["fixtures"])], cols, 150, top, RH, True, "#f2f2f2", f85)
    _row(ta, n + 2, [None, None, "CABLE SIZE: " + c["cable"], "TOTAL LENGTH", f"{c['length']:.0f} m"], cols, 150, top, RH, True, "#e2f0d9", f85)
    for cc in cols:
        ta.plot([cc, cc], [top - (n + 3) * RH, top], c="k", lw=0.6)
    ta.plot([0, 150], [top - (n + 3) * RH] * 2, c="k", lw=1.2)
    ph = c["phase"]
    x0 = (0.02 + wf + 0.03) * W
    wid = W - x0 - 0.2
    fs = 9.5 * K
    y = 2.34 * kg

    def put(txt, size, color="k", bold=False):
        nonlocal y
        t = _wrap(txt, wid, size)
        fig.text(x0 / W, y / H, t, fontsize=size, weight="bold" if bold else "normal", color=color, va="top")
        y -= (0.14 * size / 9.5 * (t.count("\n") + 1) + 0.2) * kg
    put("LOAD BALANCE (from Excel fixtures)", 10 * K, bold=True)
    put("   ".join(f"{k}: {v:g} W" for k, v in ph.items()) + f"   Total: {sum(ph.values()):g} W", fs)
    put(f"Number of poles/JBs: {len(poles)}   Cable runs: {len(poles)} (incl. panel to first pole)", fs)
    put(f"Cable size: {c['cable']}   Total cable: {c['length']:.0f} m", fs)
    xl = c.get("excel_loads") or {}
    if xl:
        put("Excel TOTAL LOAD: " + "  ".join(f"{k} {v:g}" for k, v in xl.items()), 8 * K, "#666")


def _rows(cs):
    def f(ax, i, vals, xs, x1, y_top, rh, bold=False, fill=None, fs=9):
        return _row(ax, i, vals, xs, x1, y_top, rh, bold, fill, fs * cs)
    return f


def cover_figs(S, built, syms):
    O = S["out"]
    cs = list(built["circuits"].values())
    types, cable = core.overall(S, built)
    names = list(types)
    figs = []
    W_, H_ = render.new_fig(S).get_size_inches(); plt.close("all")
    kk = max(0.8, min(W_, H_) / 11.69)
    csc = min(0.94 * W_ / 220, 0.85 * H_ / 140) / (0.94 * 16.54 / 220)
    row = _rows(csc)
    # ---- page 1: MTO by circuit
    fig = render.new_fig(S)
    ax = fig.add_axes([0.03, 0.03, 0.94, 0.85]); ax.set_aspect("equal"); ax.axis("off"); ax.set_xlim(0, 220); ax.set_ylim(0, 140)
    fig.text(0.03, 0.95, f"{O['title']} - COVER SHEET (1/2) - MTO BY CIRCUIT", fontsize=20 * kk, weight="bold")
    fig.text(0.03, 0.925, f"Source: Excel circuiting / load balance workbook   |   cable lengths as per Excel   |   {len(cs)} circuits, "
             f"{sum(len(c['poles']) for c in cs)} poles", fontsize=10 * kk, color="#444")
    fixed = [22, 14, 15, 16]
    tail = [18, 28, 20]
    cw = (220 - sum(fixed) - sum(tail) - 40) / max(len(names), 1)
    widths = fixed[:1] + fixed[1:2] + [40] + fixed[2:] + [cw] * len(names) + tail
    cx = [0]
    for w in widths:
        cx.append(cx[-1] + w)
    hd = ["PANEL", "CCT", "AREA", "POLES", "FIXTURES"] + names + ["LOAD (W)", "CABLE SIZE", "LENGTH (m)"]
    RH, top = 4.6, 126
    ax.plot([0, 220], [top, top], c="k", lw=1.2)
    row(ax, 0, hd, cx, 220, top, RH, True, "#d9e2f3", 7.5 * csc)
    for n, c in enumerate(cs, 1):
        area = c["area"].split("|")[0].replace("AREA NAME :", "").replace("AREA NAME", "").strip(" :")[:24]
        row(ax, n, [c["key"][0], c["key"][1], area, str(len(c["poles"])), str(c["fixtures"])] +
             [f"{c['types'].get(t, [0, 0])[0]}/{c['types'].get(t, [0, 0])[1]}" for t in names] +
             [f"{sum(c['phase'].values()):g}", c["cable"], f"{c['length']:.0f}"], cx, 220, top, RH, fs=7.5 * csc)
    N = len(cs) + 1
    row(ax, N, ["TOTAL", "", "", str(sum(len(c["poles"]) for c in cs)), str(sum(c["fixtures"] for c in cs))] +
         [f"{types[t][0]}/{types[t][1]}" for t in names] +
         [f"{sum(sum(c['phase'].values()) for c in cs):g}", "", f"{sum(c['length'] for c in cs):.0f}"], cx, 220, top, RH, True, "#f2f2f2", 7.5 * csc)
    for x in cx:
        ax.plot([x, x], [top - (N + 1) * RH, top], c="k", lw=0.6)
    ax.plot([0, 220], [top - (N + 1) * RH] * 2, c="k", lw=1.2)
    ax.text(0, top - (N + 1) * RH - 3, "Type columns show poles / fixtures.  Normal = ...BLL40 panels, Emergency = ...BNL40 panels.",
            fontsize=8 * csc, color="#555", va="top")
    figs.append(fig)
    # ---- page 2: overall MTO + cable + load by kind
    fig = render.new_fig(S)
    ax = fig.add_axes([0.03, 0.03, 0.94, 0.85]); ax.set_aspect("equal"); ax.axis("off"); ax.set_xlim(0, 220); ax.set_ylim(0, 140)
    fig.text(0.03, 0.95, f"{O['title']} - COVER SHEET (2/2) - OVERALL MTO", fontsize=20 * kk, weight="bold")
    R2, y2 = 7.2, 120
    ax.text(0, y2 + 2, "OVERALL MTO - FIXTURES", fontsize=11 * csc, weight="bold", va="bottom")
    c2 = [0, 16, 50, 80, 110]
    ax.plot([0, 110], [y2, y2], c="k", lw=1.2)
    row(ax, 0, ["ITEM", "FIXTURE TYPE", "QTY (POLES)", "QTY (FIXTURES)"], c2, 110, y2, R2, True, "#d9e2f3")
    tp = sum(len(c["poles"]) for c in cs)
    for n, t in enumerate(names, 1):
        row(ax, n, [str(n), "          " + t, str(types[t][0]), str(types[t][1])], c2, 110, y2, R2)
        draw_sym(ax, 22, y2 - n * R2 - R2 / 2, syms.get(t), 0.42, 0.5, O["bw_symbols"])
    k = len(names) + 1
    row(ax, k, ["", "TOTAL", str(tp), str(sum(v[1] for v in types.values()))], c2, 110, y2, R2, True, "#f2f2f2")
    row(ax, k + 1, [str(k), "          LIGHTING JB", str(tp), "-"], c2, 110, y2, R2)
    ax.add_patch(Rectangle((19.5, y2 - (k + 1) * R2 - R2 / 2 - 1.6), 3.2, 3.2, fc="white", ec="k", lw=1.6))
    for x in c2:
        ax.plot([x, x], [y2 - (k + 2) * R2, y2], c="k", lw=0.6)
    ax.plot([0, 110], [y2 - (k + 2) * R2] * 2, c="k", lw=1.2)
    ax.text(125, y2 + 2, "OVERALL MTO - CABLE", fontsize=11 * csc, weight="bold", va="bottom")
    c3 = [125, 155, 185, 220]
    ax.plot([125, 220], [y2, y2], c="k", lw=1.2)
    row(ax, 0, ["CABLE SIZE", "CIRCUITS", "TOTAL LENGTH (m)"], c3, 220, y2, R2, True, "#e2f0d9")
    for n, (sz, (cn, ln)) in enumerate(cable.items(), 1):
        row(ax, n, [sz, str(cn), f"{ln:.0f}"], c3, 220, y2, R2)
    m = len(cable) + 1
    row(ax, m, ["TOTAL", str(len(cs)), f"{sum(c['length'] for c in cs):.0f}"], c3, 220, y2, R2, True, "#f2f2f2")
    for x in c3:
        ax.plot([x, x], [y2 - (m + 1) * R2, y2], c="k", lw=0.6)
    ax.plot([125, 220], [y2 - (m + 1) * R2] * 2, c="k", lw=1.2)
    # by panel kind
    y3 = y2 - (k + 2) * R2 - 14
    ax.text(0, y3 + 2, "CABLE AND LOAD BY PANEL", fontsize=11 * csc, weight="bold", va="bottom")
    pk = collections.OrderedDict()
    for c in cs:
        d = pk.setdefault(c["key"][0], [0, 0, 0, 0.0, c["kind"]])
        d[0] += 1; d[1] += len(c["poles"]); d[2] += sum(c["phase"].values()); d[3] += c["length"]
    c4 = [0, 30, 60, 90, 130, 170, 220]
    ax.plot([0, 220], [y3, y3], c="k", lw=1.2)
    row(ax, 0, ["PANEL", "TYPE", "CIRCUITS", "POLES", "LOAD (W)", "CABLE LENGTH (m)"], c4, 220, y3, 6.2, True, "#d9e2f3", 8.5 * csc)
    for n, (pn, d) in enumerate(pk.items(), 1):
        row(ax, n, [pn, d[4].title(), str(d[0]), str(d[1]), f"{d[2]:g}", f"{d[3]:.0f}"], c4, 220, y3, 6.2, fs=8.5 * csc)
    for x in c4:
        ax.plot([x, x], [y3 - (len(pk) + 1) * 6.2, y3], c="k", lw=0.6)
    ax.plot([0, 220], [y3 - (len(pk) + 1) * 6.2] * 2, c="k", lw=1.2)
    figs.append(fig)
    return figs


def cover_project(S, built, syms):
    """Title page: project name, drawing number, revision block and a short summary."""
    O = S["out"]
    P = S.get("project", {})
    fig = render.new_fig(S)
    W, H = fig.get_size_inches()
    kk = max(0.8, min(W, H) / 11.69)
    cs = list(built["circuits"].values())
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off"); ax.set_xlim(0, W); ax.set_ylim(0, H)
    m = 0.06 * min(W, H)
    ax.add_patch(Rectangle((m, m), W - 2 * m, H - 2 * m, fc="none", ec="k", lw=2.0))
    ax.add_patch(Rectangle((m * 1.25, m * 1.25), W - 2.5 * m, H - 2.5 * m, fc="none", ec="k", lw=0.6))
    cx = W / 2
    y = H * 0.80
    ax.text(cx, y, O["title"], ha="center", va="center", fontsize=34 * kk, weight="bold")
    ax.plot([cx - W * 0.3, cx + W * 0.3], [y - 0.55 * kk, y - 0.55 * kk], c="k", lw=1.5)
    y -= 1.5 * kk
    ax.text(cx, y, (P.get("name") or "PROJECT NAME").upper(), ha="center", va="center", fontsize=26 * kk, weight="bold", color="#1f3b73")
    if P.get("location"):
        y -= 0.8 * kk
        ax.text(cx, y, P["location"], ha="center", va="center", fontsize=14 * kk, color="#444")
    y -= 1.3 * kk
    ax.text(cx, y, "DRAWING NO.", ha="center", va="center", fontsize=11 * kk, color="#666")
    y -= 0.55 * kk
    ax.text(cx, y, P.get("drawing_no") or "-", ha="center", va="center", fontsize=24 * kk, weight="bold",
            bbox=dict(boxstyle="square,pad=0.5", fc="white", ec="k", lw=1.5))
    # info table
    rows = [("Client", P.get("client", "")), ("Revision", P.get("revision", "")), ("Date", P.get("date", "")),
            ("Prepared by", P.get("prepared", "")), ("Checked by", P.get("checked", "")), ("Approved by", P.get("approved", ""))]
    rows = [(a, b) for a, b in rows if b not in (None, "")] or [("Revision", "0")]
    tw_ = min(W - 4 * m, 9.0 * kk)
    rh = 0.52 * kk
    y0 = y - 1.4 * kk
    x0 = cx - tw_ / 2
    for i, (a, b) in enumerate(rows):
        yy = y0 - i * rh
        ax.add_patch(Rectangle((x0, yy - rh), tw_ * 0.32, rh, fc="#d9e2f3", ec="k", lw=0.8))
        ax.add_patch(Rectangle((x0 + tw_ * 0.32, yy - rh), tw_ * 0.68, rh, fc="white", ec="k", lw=0.8))
        ax.text(x0 + 0.12 * kk, yy - rh / 2, a, va="center", fontsize=11 * kk, weight="bold")
        ax.text(x0 + tw_ * 0.32 + 0.12 * kk, yy - rh / 2, str(b), va="center", fontsize=11 * kk)
    yy = y0 - len(rows) * rh - 1.0 * kk
    types, cable = core.overall(S, built)
    tp = sum(len(c["poles"]) for c in cs)
    tf = sum(c["fixtures"] for c in cs)
    load = sum(sum(c["phase"].values()) for c in cs)
    ln = sum(c["length"] for c in cs)
    summ = [f"{len(cs)} circuits  |  {tp} poles / lighting JB  |  {tf} fixtures",
            f"Total connected load {load:g} W  |  total cable {ln:.0f} m  |  drawing scale 1:{S['scale']}",
            f"Paper {O.get('paper')} {O.get('orientation')}  |  layout {O.get('layout_dir')}  |  cable {', '.join(cable) if cable else '-'}"]
    for i, t in enumerate(summ):
        ax.text(cx, yy - i * 0.5 * kk, t, ha="center", va="center", fontsize=11 * kk, color="#333")
    if P.get("note"):
        ax.text(cx, yy - 2.0 * kk, _wrap(P["note"], W - 4 * m, 10 * kk), ha="center", va="top", fontsize=10 * kk, color="#555")
    ax.text(cx, 2.1 * m, "Generated by Loop Diagram Builder from the circuiting / load balance workbook", ha="center", fontsize=8 * kk, color="#888")
    return fig


def sheet_figure_excel(S, built, key, syms):
    if key == "project":
        return cover_project(S, built, syms)
    if key is None:
        return cover_figs(S, built, syms)[0]
    if key == "cover2":
        return cover_figs(S, built, syms)[1]
    fig = render.new_fig(S)
    draw_tree_sheet(fig, S, built["circuits"][key], syms, common_scale(S, built, syms))
    return fig


def sheet_keys(S, built):
    return (["project"] if S["out"].get("cover_page", True) else []) + [None, "cover2"] + list(built["circuits"])


def export_pdf_excel(path, S, built):
    syms = render.Symbols(S)
    common_scale(S, built, syms)
    with PdfPages(path) as pdf:
        if S["out"].get("cover_page", True):
            f = cover_project(S, built, syms)
            pdf.savefig(f); plt.close(f)
        for f in cover_figs(S, built, syms):
            pdf.savefig(f); plt.close(f)
        for key in built["circuits"]:
            fig = sheet_figure_excel(S, built, key, syms)
            pdf.savefig(fig); plt.close(fig)
