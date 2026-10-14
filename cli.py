import argparse, os, sys
import settings, core, render

def run(argv=None):
    ap = argparse.ArgumentParser(description="Loop Diagram Builder (command line). Input: marked-up PDF or the circuiting Excel workbook")
    ap.add_argument("input"); ap.add_argument("--out", default="Looping_Diagram.pdf")
    ap.add_argument("--xlsx", default=None); ap.add_argument("--settings", default=None)
    ap.add_argument("--tagcheck", action="store_true", help="duplicate / suspicious tag check on a PDF with text tags")
    ap.add_argument("--verify", action="store_true", help="verify the Excel workbook (mismatches, missing values, totals); report goes to --xlsx")
    ap.add_argument("--paper", default=None, help="A4 A3 A2 A1 A0 Letter Tabloid")
    ap.add_argument("--orientation", default=None, choices=["landscape", "portrait"])
    ap.add_argument("--layout", default=None, choices=["horizontal", "vertical"])
    ap.add_argument("--no-cover", action="store_true", help="omit the project cover page")
    ap.add_argument("--project", default=None); ap.add_argument("--drawing-no", default=None)
    a = ap.parse_args(argv)
    if a.verify:
        import excel_verify
        S0 = settings.load(a.settings)
        issues, msg = excel_verify.run(S0, a.input, a.xlsx or "Excel_Verification.xlsx")
        for d in issues[:40]:
            print(f"{d['severity']:7} {d['category']:13} {d['sheet']} row {d['row']} {d['tag']}: {d['message']}")
        if len(issues) > 40: print(f"... {len(issues)-40} more in the report")
        print(msg); return
    if a.tagcheck:
        import tagcheck
        res, msg = tagcheck.run(a.input, a.out if a.out != "Looping_Diagram.pdf" else "Tag_Check_Marked.pdf", a.xlsx or "Tag_Check.xlsx")
        print(msg); return
    S = settings.load(a.settings)
    if a.paper: S["out"]["paper"] = a.paper
    if a.orientation: S["out"]["orientation"] = a.orientation
    if a.layout: S["out"]["layout_dir"] = a.layout
    if a.no_cover: S["out"]["cover_page"] = False
    if a.project: S["project"]["name"] = a.project
    if a.drawing_no: S["project"]["drawing_no"] = a.drawing_no
    if a.input.lower().endswith((".xlsx", ".xlsm")):
        import excel_reader
        built = excel_reader.build_excel(S, excel_reader.read_workbook(a.input))
        export_x = excel_reader.export_xlsx
    else:
        built = core.build(S, core.read_pdf(a.input, S))
        export_x = core.export_xlsx
    render.export_pdf(a.out, S, built)
    if a.xlsx:
        export_x(a.xlsx, S, built)
    print("\n".join(built["checks"]))
    print("Saved", a.out)

if __name__ == "__main__":
    run()
