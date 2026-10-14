"""Excel verification: finds mismatches and missing values in the circuiting / load balance workbook.
Command line:  python app.py --cli --verify workbook.xlsx [--xlsx report.xlsx]"""
import re, collections
import excel_reader as E

TAGRX = E.TAGRX
SEV = {"ERROR": 0, "WARNING": 1, "INFO": 2}


def _circ_of(b):
    first = b["rows"][0]
    m = TAGRX.match(first["tag"])
    panel = m.group("panel") if m else first["panel"]
    cct = m.group("cct") if m else re.sub(r"\D", "", first["circuit"])
    return panel, cct


def verify(S, blocks, expected_total_w=0.0):
    """returns (issues, circuit_rows). issue = dict(severity, category, sheet, row, panel, circuit, tag, message)"""
    V = S.get("verify", {})
    known = {ft["name"] for ft in S["fixture_types"]}
    max_span = float(V.get("max_span_m", S.get("long_span_warn_m", 45.0)) or 0)
    issues, circ_rows = [], []
    all_tags = collections.defaultdict(list)

    def add(sev, cat, b, rw, msg, panel="", cct="", tag=""):
        issues.append(dict(severity=sev, category=cat, sheet=b["sheet"], row=(rw or {}).get("row", ""), panel=panel, circuit=cct,
                           tag=tag or (rw or {}).get("tag", ""), message=msg))
    watt_by_type = collections.defaultdict(collections.Counter)
    for b in blocks:
        poles, _ = E.build_poles(b)
        for p in poles:
            if p["type"]:
                watt_by_type[p["type"]][round((p["watt"] or 0) / max(len(p["rows"]), 1), 3)] += 1
    usual = {t: c.most_common(1)[0][0] for t, c in watt_by_type.items()}
    grand = 0.0
    for b in blocks:
        panel, cct = _circ_of(b)
        poles, warns = E.build_poles(b)
        rows = b["rows"]
        # ---- missing values
        for rw in rows:
            m = TAGRX.match(rw["tag"])
            if not m:
                add("ERROR", "Tag format", b, rw, f"tag '{rw['tag']}' does not look like PANEL/01L1-01", panel, cct)
            if not rw["panel"]:
                add("WARNING", "Missing value", b, rw, "PANEL column is empty", panel, cct)
            if not rw["circuit"]:
                add("WARNING", "Missing value", b, rw, "CIRCUIT column is empty", panel, cct)
            if not (rw["watt"] or 0) > 0:
                add("ERROR", "Missing value", b, rw, "watt is empty or zero", panel, cct)
            if not rw["phase"]:
                add("WARNING", "Missing value", b, rw, "PHASES column is empty", panel, cct)
        for i, p in enumerate(poles):
            first = p["rows"][0]
            if not p["type"]:
                add("ERROR", "Missing value", b, first, "no fixture type", panel, cct, p["tag"])
            elif p["type"] not in known:
                add("ERROR", "Mismatch", b, first, f"fixture type '{p['type']}' is not in Settings -> Fixture types (known: {', '.join(sorted(known))})", panel, cct, p["tag"])
            if p["length"] is None:
                add("ERROR", "Missing value", b, first, "no cable length" + (" (panel to first pole)" if i == 0 else ""), panel, cct, p["tag"])
            elif p["length"] <= 0:
                add("ERROR", "Mismatch", b, first, f"cable length is {p['length']}", panel, cct, p["tag"])
            elif max_span and p["length"] > max_span:
                add("WARNING", "Length", b, first, f"span {p['length']} m is longer than {max_span:g} m", panel, cct, p["tag"])
            if i > 0 and not p["frm"]:
                add("ERROR", "Missing value", b, first, "FROM column is empty (previous pole assumed)", panel, cct, p["tag"])
            for extra in p["rows"][1:]:
                if extra["frm"] or extra["length"] is not None:
                    add("WARNING", "Missing value", b, extra, "row has FROM / length but no fixture type, so it was treated as a 2nd fixture on the previous pole", panel, cct, extra["tag"])
            u = usual.get(p["type"])
            if u:
                per = round((p["watt"] or 0) / max(len(p["rows"]), 1), 3)
                if abs(per - u) > float(V.get("watt_tolerance", 0.0)):
                    add("WARNING", "Mismatch", b, first, f"{p['type']}: {per:g} W per fixture, other {p['type']} poles use {u:g} W", panel, cct, p["tag"])
        for w in warns:
            if "FROM '" in w:
                tag = w.split(":")[0]
                add("ERROR", "Mismatch", b, next((r for r in rows if r["tag"] == tag.split("/")[0] + "/" + tag.split("/")[1]), None) if "/" in tag else None,
                    "FROM refers to a tag that is not above it in this circuit: " + w.split(": ", 1)[1], panel, cct, tag)
        # ---- tag / column mismatches
        phase_w = collections.OrderedDict()
        nums = collections.defaultdict(list)
        for rw in rows:
            m = TAGRX.match(rw["tag"])
            if not m:
                continue
            all_tags[rw["tag"]].append((b, rw))
            if m.group("panel").replace(" ", "") != rw["panel"].replace(" ", "") and rw["panel"]:
                add("ERROR", "Mismatch", b, rw, f"tag panel {m.group('panel')} but PANEL column says {rw['panel']}", panel, cct)
            cc = re.sub(r"\D", "", rw["circuit"])
            if rw["circuit"] and cc and int(cc) != int(m.group("cct")):
                add("ERROR", "Mismatch", b, rw, f"tag circuit {m.group('cct')} but CIRCUIT column says {rw['circuit']}", panel, cct)
            ph = "L" + m.group("ph")
            if rw["phase"] and rw["phase"] != ph:
                add("WARNING", "Mismatch", b, rw, f"PHASES column says {rw['phase']} but tag says {ph}", panel, cct)
            phase_w[ph] = phase_w.get(ph, 0) + (rw["watt"] or 0)
            nums[ph].append(int(m.group("no")))
        for ph, ns in nums.items():
            cnt = collections.Counter(ns)
            miss = [n for n in range(1, max(ns) + 1) if n not in cnt]
            if miss:
                add("WARNING", "Numbering", b, None, f"phase {ph}: fixture number(s) {', '.join(f'{n:02d}' for n in miss)} missing in the sequence 01..{max(ns):02d}", panel, cct)
            for n, k in cnt.items():
                if k > 1:
                    add("ERROR", "Duplicate", b, None, f"phase {ph}: fixture number {n:02d} used {k} times", panel, cct)
        tags = [r["tag"] for r in rows]
        for t, k in collections.Counter(tags).items():
            if k > 1:
                add("ERROR", "Duplicate", b, next(r for r in rows if r["tag"] == t), f"fixture tag appears {k} times in this circuit", panel, cct, t)
        # ---- totals
        length = sum(p["length"] or 0 for p in poles)
        if b["xl_length"] is not None and abs(b["xl_length"] - length) > 0.5:
            add("ERROR", "Total", b, None, f"sum of lengths {length:g} m differs from the Excel length total {b['xl_length']:g} m", panel, cct)
        for k, v in b["loads"].items():
            mm = re.search(r"L(\d)$", k)
            if mm:
                ph = "L" + mm.group(1)
                if abs((phase_w.get(ph, 0)) - v) > 0.5:
                    add("ERROR", "Total", b, None, f"{ph} load: fixtures add up to {phase_w.get(ph, 0):g} W but the Excel TOTAL LOAD row says {v:g} W", panel, cct)
        tot_cct = sum(phase_w.values())
        xl_tot = next((v for k, v in b["loads"].items() if not re.search(r"L\d$", k)), None)
        if xl_tot is not None and abs(xl_tot - tot_cct) > 0.5:
            add("ERROR", "Total", b, None, f"circuit total: fixtures add up to {tot_cct:g} W but Excel says {xl_tot:g} W", panel, cct)
        grand += tot_cct
        circ_rows.append(dict(sheet=b["sheet"], panel=panel, circuit=cct, poles=len(poles), fixtures=len(rows), watt=tot_cct,
                              L1=phase_w.get("L1", 0), L2=phase_w.get("L2", 0), L3=phase_w.get("L3", 0), length=length,
                              xl_length=b["xl_length"], xl_load=xl_tot))
    for t, lst in all_tags.items():
        if len({id(b) for b, _ in lst}) > 1:
            add("ERROR", "Duplicate", lst[0][0], lst[0][1], "same fixture tag also used in " + ", ".join(sorted({f"{b['sheet']} row {r['row']}" for b, r in lst[1:]})))
    exp = float(expected_total_w or V.get("expected_total_w", 0) or 0)
    if exp and abs(grand - exp) > 0.5:
        issues.append(dict(severity="ERROR", category="Total", sheet="(all)", row="", panel="", circuit="", tag="",
                           message=f"total load of all circuits is {grand:g} W but the expected value is {exp:g} W"))
    issues.sort(key=lambda d: (SEV[d["severity"]], d["category"], d["sheet"], d["row"] if isinstance(d["row"], int) else 0))
    return issues, circ_rows, grand


def export_xlsx(path, issues, circ_rows, grand, source=""):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()
    ws = wb.active; ws.title = "Summary"
    ws.append(["Excel verification" + (f" - {source}" if source else "")]); ws["A1"].font = Font(bold=True, size=14, name="Arial")
    ws.append([])
    cnt = collections.Counter((d["severity"], d["category"]) for d in issues)
    ws.append(["Severity", "Category", "Count"])
    for (sev, cat), n in sorted(cnt.items(), key=lambda kv: (SEV[kv[0][0]], kv[0][1])):
        ws.append([sev, cat, n])
    ws.append([]); ws.append(["Total issues", len(issues)])
    ws.append(["Circuits checked", len(circ_rows)])
    ws.append(["Total load of all circuits (W)", grand])
    ws.append(["Total cable length (m)", sum(r["length"] for r in circ_rows)])
    ws.append([]); ws.append(["Result", "NO PROBLEMS FOUND" if not issues else f"{sum(1 for d in issues if d['severity'] == 'ERROR')} errors, {sum(1 for d in issues if d['severity'] == 'WARNING')} warnings"])
    ws2 = wb.create_sheet("Issues")
    ws2.append(["Severity", "Category", "Sheet", "Excel row", "Panel", "Circuit", "Tag", "Problem"])
    fills = {"ERROR": "F8CBAD", "WARNING": "FFE699", "INFO": "DDEBF7"}
    for d in issues:
        ws2.append([d["severity"], d["category"], d["sheet"], d["row"], d["panel"], d["circuit"], d["tag"], d["message"]])
        ws2.cell(ws2.max_row, 1).fill = PatternFill("solid", fgColor=fills[d["severity"]])
    ws2.auto_filter.ref = ws2.dimensions
    ws3 = wb.create_sheet("Circuit totals")
    ws3.append(["Sheet", "Panel", "Circuit", "Poles", "Fixtures", "L1 (W)", "L2 (W)", "L3 (W)", "Load (W)", "Excel load (W)", "Load diff", "Length (m)", "Excel length (m)", "Length diff"])
    for r in circ_rows:
        n = ws3.max_row + 1
        ws3.append([r["sheet"], r["panel"], r["circuit"], r["poles"], r["fixtures"], r["L1"], r["L2"], r["L3"], f"=SUM(F{n}:H{n})", r["xl_load"],
                    f'=IF(J{n}="","",I{n}-J{n})', r["length"], r["xl_length"], f'=IF(M{n}="","",L{n}-M{n})'])
    n = ws3.max_row + 1
    ws3.append(["TOTAL", "", "", f"=SUM(D2:D{n-1})", f"=SUM(E2:E{n-1})", f"=SUM(F2:F{n-1})", f"=SUM(G2:G{n-1})", f"=SUM(H2:H{n-1})", f"=SUM(I2:I{n-1})", "", "",
                f"=SUM(L2:L{n-1})"])
    for w in wb.worksheets:
        for c in (w[1] if w.title != "Summary" else []):
            c.font = Font(bold=True, color="FFFFFF", name="Arial"); c.fill = PatternFill("solid", fgColor="1F4E78")
        for col in w.columns:
            w.column_dimensions[col[0].column_letter].width = max(10, min(70, max(len(str(c.value or "")) for c in col) + 2))
    for c in ws[3]:
        c.font = Font(bold=True, name="Arial")
    ws3[ws3.max_row][0].font = Font(bold=True, name="Arial")
    ws2.freeze_panes = "A2"
    wb.save(path)


def run(S, xlsx, out_xlsx=None, expected_total_w=0.0):
    blocks = E.read_workbook(xlsx, log=lambda *a: None)
    issues, circ, grand = verify(S, blocks, expected_total_w)
    if out_xlsx:
        export_xlsx(out_xlsx, issues, circ, grand, source=xlsx.replace("\\", "/").split("/")[-1])
    ne = sum(1 for d in issues if d["severity"] == "ERROR"); nw = sum(1 for d in issues if d["severity"] == "WARNING")
    msg = f"{len(circ)} circuits checked: {ne} errors, {nw} warnings. Total load {grand:g} W."
    return issues, msg
