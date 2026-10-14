"""Loop Diagram Builder - Windows desktop app (tkinter). Run:  python app.py
Command line (no window):  python app.py --cli drawing.pdf  (or the Excel workbook) --out Looping_Diagram.pdf --xlsx MTO.xlsx"""
import sys
if "--cli" in sys.argv:
    sys.argv.remove("--cli")
    import cli
    cli.run()
    sys.exit(0)

import os, io, base64, copy, json, threading, queue, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import settings, core, render
import matplotlib.pyplot as plt
import pdfplumber


def getp(d, path):
    for p in path:
        d = d[p]
    return d


def setp(d, path, val):
    for p in path[:-1]:
        d = d[p]
    d[path[-1]] = val


def png_image(fig, dpi):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    return tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode("ascii"))


def pil_to_photo(im):
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode("ascii"))


class ScrollCanvas(ttk.Frame):
    def __init__(self, master, **kw):
        super().__init__(master)
        self.c = tk.Canvas(self, bg="#808080", highlightthickness=0, **kw)
        xs = ttk.Scrollbar(self, orient="horizontal", command=self.c.xview)
        ys = ttk.Scrollbar(self, orient="vertical", command=self.c.yview)
        self.c.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        self.c.grid(row=0, column=0, sticky="nsew"); ys.grid(row=0, column=1, sticky="ns"); xs.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1); self.columnconfigure(0, weight=1)
        self.img = None

    def show(self, photo):
        self.img = photo
        self.c.delete("all")
        self.c.create_image(0, 0, anchor="nw", image=photo)
        self.c.configure(scrollregion=(0, 0, photo.width(), photo.height()))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Loop Diagram Builder")
        self.geometry("1400x850")
        self.S = settings.load()
        self.pdf_path = None
        self.xlsx_path = None
        self.blocks = None
        self.data = None
        self.built = None
        self.keys = []
        self.q = queue.Queue()
        bar = ttk.Frame(self); bar.pack(fill="x", padx=6, pady=4)
        for txt, cmd in [("Open PDF", self.open_pdf), ("Open Excel", self.open_excel), ("Re-read / Recalculate", self.recalc), ("Export PDF", self.export_pdf),
                         ("Export MTO (Excel)", self.export_xlsx), ("Tag Check (duplicates)", self.tag_check), ("Verify Excel", self.verify_excel), ("Settings", self.open_settings)]:
            ttk.Button(bar, text=txt, command=cmd).pack(side="left", padx=3)
        body = ttk.PanedWindow(self, orient="horizontal"); body.pack(fill="both", expand=True)
        left = ttk.Frame(body); body.add(left, weight=0)
        ttk.Label(left, text="Sheets", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=4)
        self.lb = tk.Listbox(left, width=26, exportselection=False); self.lb.pack(fill="both", expand=True, padx=4, pady=2)
        self.lb.bind("<<ListboxSelect>>", lambda e: self.preview())
        ttk.Label(left, text="Checks", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=4)
        self.chk = tk.Text(left, width=34, height=14, wrap="word"); self.chk.pack(fill="x", padx=4, pady=2)
        self.view = ScrollCanvas(body); body.add(self.view, weight=1)
        self.status = tk.StringVar(value="Open a PDF to start.")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", side="bottom")
        self.after(200, self.poll)

    # ---- background work
    def poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "done":
                    self.data, self.built = payload
                    self.fill_list()
                    self.status.set(f"{len(self.data['poles'])} tags read, {len(self.built['circuits'])} circuits, {len(self.built['checks'])} checks.")
                    self.config(cursor="")
                elif kind == "xdone":
                    self.blocks, self.built = payload
                    self.data = None
                    self.fill_list()
                    self.status.set(f"Excel read: {len(self.built['circuits'])} circuits, {sum(len(c['poles']) for c in self.built['circuits'].values())} poles, {len(self.built['checks'])} checks.")
                    self.config(cursor="")
                elif kind == "calc":
                    self.built = payload
                    self.fill_list()
                    self.status.set("Recalculated.")
                    self.config(cursor="")
                elif kind == "msg":
                    self.status.set(payload)
                elif kind == "err":
                    self.config(cursor="")
                    self.status.set("Error")
                    messagebox.showerror("Error", payload)
        except queue.Empty:
            pass
        self.after(200, self.poll)

    def open_pdf(self):
        p = filedialog.askopenfilename(title="Open marked-up PDF", filetypes=[("PDF", "*.pdf")])
        if not p:
            return
        self.pdf_path = p
        self.read_pdf()

    def open_excel(self):
        p = filedialog.askopenfilename(title="Open circuiting / load balance workbook", filetypes=[("Excel", "*.xlsx *.xlsm")])
        if not p:
            return
        self.xlsx_path = p
        self.pdf_path = self.pdf_path
        self.config(cursor="watch"); self.status.set("Reading Excel...")
        S = copy.deepcopy(self.S)

        def work():
            try:
                import excel_reader
                blocks = excel_reader.read_workbook(p)
                self.q.put(("xdone", (blocks, excel_reader.build_excel(S, blocks))))
            except Exception:
                self.q.put(("err", traceback.format_exc()))
        threading.Thread(target=work, daemon=True).start()

    def read_pdf(self):
        if not self.pdf_path:
            return messagebox.showinfo("Loop Diagram Builder", "Open a PDF first.")
        self.config(cursor="watch"); self.status.set("Reading PDF (large drawings can take a minute)...")
        S = copy.deepcopy(self.S)

        def work():
            try:
                data = core.read_pdf(self.pdf_path, S, log=lambda m: self.q.put(("msg", m)))
                self.q.put(("done", (data, core.build(S, data))))
            except Exception:
                self.q.put(("err", traceback.format_exc()))
        threading.Thread(target=work, daemon=True).start()

    def recalc(self):
        """Re-calculate from tags already read (use after changing scale, tag format, cable sizes...)."""
        S = copy.deepcopy(self.S)
        if self.built and self.built.get("source") == "excel" and self.blocks is not None:
            import excel_reader
            self.q.put(("calc", excel_reader.build_excel(S, self.blocks)))
            return
        if self.data is None:
            return self.read_pdf()
        try:
            self.q.put(("calc", core.build(S, self.data)))
        except Exception:
            self.q.put(("err", traceback.format_exc()))

    def fill_list(self):
        self.lb.delete(0, "end")
        if self.built.get("source") == "excel":
            self.keys = [None, "cover2"] + list(self.built["circuits"])
            self.lb.insert("end", "Cover sheet 1/2 - MTO by circuit")
            self.lb.insert("end", "Cover sheet 2/2 - overall MTO")
            for k in self.keys[2:]:
                self.lb.insert("end", self.built["circuits"][k]["label"])
        else:
            self.keys = [None] + list(self.built["circuits"])
            self.lb.insert("end", "Cover sheet / overall MTO")
            for k in self.keys[1:]:
                c = self.built["circuits"][k]
                self.lb.insert("end", f"{k[0]} / {k[1]}   ({len(c['poles'])} poles)")
        self.chk.delete("1.0", "end")
        self.chk.insert("end", "\n".join("- " + c for c in self.built["checks"]) or "No problems found.")
        self.lb.selection_set(0)
        self.preview()

    def preview(self):
        if not self.built:
            return
        sel = self.lb.curselection()
        key = self.keys[sel[0] if sel else 0]
        self.status.set("Drawing preview...")
        self.update_idletasks()
        fig = render.sheet_figure(self.S, self.built, key, render.Symbols(self.S))
        self.view.show(png_image(fig, 80))
        plt.close(fig)
        self.status.set("Ready.")

    def export_pdf(self):
        if not self.built:
            return messagebox.showinfo("Loop Diagram Builder", "Nothing to export yet.")
        p = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], initialfile="Looping_Diagram.pdf")
        if p:
            self.status.set("Writing PDF...")
            self.update_idletasks()
            render.export_pdf(p, self.S, self.built)
            self.status.set("Saved " + p)

    def export_xlsx(self):
        if not self.built:
            return messagebox.showinfo("Loop Diagram Builder", "Nothing to export yet.")
        p = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")], initialfile="MTO.xlsx")
        if p:
            if self.built.get("source") == "excel":
                import excel_reader
                excel_reader.export_xlsx(p, self.S, self.built)
            else:
                core.export_xlsx(p, self.S, self.built)
            self.status.set("Saved " + p)

    def tag_check(self):
        p = filedialog.askopenfilename(title="PDF with new tags as text (e.g. TAGG UPDATED)", filetypes=[("PDF", "*.pdf")])
        if not p:
            return
        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], initialfile="Tag_Check_Marked.pdf", title="Save marked PDF")
        if not out:
            return
        import tagcheck
        try:
            res, msg = tagcheck.run(p, out, os.path.splitext(out)[0] + ".xlsx")
        except Exception:
            return messagebox.showerror("Tag check", traceback.format_exc())
        self.status.set(msg)
        messagebox.showinfo("Tag check", msg + "\n\nSaved:\n" + out + "\n" + os.path.splitext(out)[0] + ".xlsx")

    def verify_excel(self):
        p = filedialog.askopenfilename(title="Circuiting / load balance Excel", filetypes=[("Excel", "*.xlsx *.xlsm")])
        if not p:
            return
        out = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")], initialfile="Excel_Verification.xlsx", title="Save verification report")
        if not out:
            return
        import excel_verify
        try:
            issues, msg = excel_verify.run(self.S, p, out)
        except Exception:
            return messagebox.showerror("Verify Excel", traceback.format_exc())
        self.status.set(msg)
        messagebox.showinfo("Verify Excel", msg + "\n\nReport (mismatches, missing values, totals):\n" + out)

    def open_settings(self):
        SettingsDialog(self)


class SettingsDialog(tk.Toplevel):
    FIELDS = {
        "Drawing & length": [
            ("Drawing scale 1 :", ("scale",), "float"), ("Paper factor (1 = PDF plotted at 100 %)", ("paper_factor",), "float"),
            ("Length multiplier", ("length_multiplier",), "float"), ("Extra length per span (m)", ("extra_per_span_m",), "float"),
            ("Warn if span longer than (m)", ("long_span_warn_m",), "float"), ("PDF page (0 = first)", ("page",), "int")],
        "Tags & reading": [
            ("New tag pattern (regex)", ("tag_regex",), "str"), ("Old tag first-line pattern (regex)", ("old_tag_regex",), "str"),
            ("Phase order (comma separated)", ("phase_order",), "list"), ("JB tag suffix", ("jb_suffix",), "str"),
            ("JB label on sheet", ("jb_label",), "str"), ("Cable tag format ({panel} {cct} {n})", ("cable_tag",), "str"),
            ("Annotation type holding new tags", ("annot_subtype",), "str"), ("Leader line colour R,G,B (0-1)", ("leader_color",), "color"),
            ("Max leader-to-box distance", ("match_tol",), "float"), ("Text gap (splits text pieces)", ("text_gap",), "float")],
        "Page & layout": [
            ("Paper size", ("out", "paper"), "choice", ["A4", "A3", "A2", "A1", "A0", "Letter", "Tabloid", "Custom"]),
            ("Orientation", ("out", "orientation"), "choice", ["landscape", "portrait"]),
            ("Diagram direction", ("out", "layout_dir"), "choice", ["horizontal", "vertical"]),
            ("Project cover page", ("out", "cover_page"), "bool"),
            ("Symbol size (inch per drawing unit, 0 = largest that fits)", ("out", "symbol_inches_per_unit"), "float"),
            ("Custom page width (in)", ("out", "page_w_in"), "float"), ("Custom page height (in)", ("out", "page_h_in"), "float")],
        "Project": [
            ("Project name", ("project", "name"), "str"), ("Drawing no.", ("project", "drawing_no"), "str"),
            ("Client", ("project", "client"), "str"), ("Location", ("project", "location"), "str"),
            ("Revision", ("project", "revision"), "str"), ("Date", ("project", "date"), "str"),
            ("Prepared by", ("project", "prepared"), "str"), ("Checked by", ("project", "checked"), "str"),
            ("Approved by", ("project", "approved"), "str"), ("Note", ("project", "note"), "str")],
        "Excel verification": [
            ("Warn if span longer than (m, 0 = off)", ("verify", "max_span_m"), "float"),
            ("Watt tolerance per fixture type (W)", ("verify", "watt_tolerance"), "float"),
            ("Expected total load of all circuits (W, 0 = skip)", ("verify", "expected_total_w"), "float")],
        "Output": [
            ("Title", ("out", "title"), "str"), ("Source note on cover", ("out", "source_note"), "str"),
            ("Poles per row", ("out", "per_row"), "int"), ("Horizontal spacing", ("out", "dx"), "float"),
            ("Row spacing", ("out", "dy"), "float"), ("Symbol scale", ("out", "symbol_scale"), "float"),
            ("Tag box fill", ("out", "tag_fill"), "str"), ("Tag box edge", ("out", "tag_edge"), "str"),
            ("Tag text colour", ("out", "tag_text"), "str"), ("Cable line colour", ("out", "line_color"), "str"),
            ("Length text colour", ("out", "length_color"), "str"),
            ("Symbols black and white", ("out", "bw_symbols"), "bool"), ("Show old tag", ("out", "show_old_tag"), "bool"),
            ("Show JB tag", ("out", "show_jb_tag"), "bool"), ("Show cable tag", ("out", "show_cable_tag"), "bool")],
    }

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Settings")
        self.geometry("760x560")
        self.S = copy.deepcopy(app.S)
        self.vars = {}
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=6, pady=6)
        for tab, fields in self.FIELDS.items():
            f = ttk.Frame(nb); nb.add(f, text=tab)
            for r, fld in enumerate(fields):
                label, path, kind = fld[:3]
                ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", padx=8, pady=3)
                v = self.make_var(getp(self.S, path), kind)
                self.vars[path] = (v, kind)
                if kind == "bool":
                    ttk.Checkbutton(f, variable=v).grid(row=r, column=1, sticky="w")
                elif kind == "choice":
                    ttk.Combobox(f, textvariable=v, values=fld[3], state="readonly", width=20).grid(row=r, column=1, sticky="w", padx=4)
                else:
                    ttk.Entry(f, textvariable=v, width=60).grid(row=r, column=1, sticky="we", padx=4)
            f.columnconfigure(1, weight=1)
        self.build_types_tab(nb)
        self.build_cable_tab(nb)
        bt = ttk.Frame(self); bt.pack(fill="x", padx=6, pady=6)
        ttk.Button(bt, text="Save", command=self.save).pack(side="right", padx=3)
        ttk.Button(bt, text="Cancel", command=self.destroy).pack(side="right", padx=3)
        ttk.Button(bt, text="Load profile...", command=self.load_profile).pack(side="left", padx=3)
        ttk.Button(bt, text="Save profile as...", command=self.save_profile).pack(side="left", padx=3)

    @staticmethod
    def make_var(val, kind):
        if kind == "bool":
            return tk.BooleanVar(value=bool(val))
        if kind in ("list", "color"):
            return tk.StringVar(value=", ".join(str(x) for x in val))
        return tk.StringVar(value=str(val))

    def collect(self):
        for path, (v, kind) in self.vars.items():
            raw = v.get()
            if kind == "float": val = float(raw)
            elif kind == "int": val = int(float(raw))
            elif kind == "bool": val = bool(raw)
            elif kind == "list": val = [x.strip() for x in raw.split(",") if x.strip()]
            elif kind == "color": val = [float(x) for x in raw.split(",")]
            else: val = raw
            setp(self.S, path, val)
        self.S["cable_sizes"] = {self.cab.set(i, "key"): self.cab.set(i, "size") for i in self.cab.get_children()}
        self.S["fixture_types"] = [dict(name=self.ft.set(i, "name"), match=self.ft.set(i, "match"), symbol=self.ft.set(i, "symbol"))
                                   for i in self.ft.get_children()]

    def save(self):
        try:
            self.collect()
        except ValueError as e:
            return messagebox.showerror("Settings", f"Please check the numbers: {e}")
        self.app.S = self.S
        settings.save(self.S)
        self.destroy()
        self.app.recalc()

    def save_profile(self):
        try:
            self.collect()
        except ValueError as e:
            return messagebox.showerror("Settings", str(e))
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Settings", "*.json")])
        if p:
            settings.save(self.S, p)

    def load_profile(self):
        p = filedialog.askopenfilename(filetypes=[("Settings", "*.json")])
        if p:
            self.app.S = settings.load(p)
            settings.save(self.app.S)
            self.destroy()
            SettingsDialog(self.app)
            self.app.recalc()

    # ---- fixture types
    def build_types_tab(self, nb):
        f = ttk.Frame(nb); nb.add(f, text="Fixture types & symbols")
        self.ft = ttk.Treeview(f, columns=("name", "match", "symbol"), show="headings", height=10)
        for c, t, w in (("name", "Type name", 120), ("match", "Found in old-tag text", 200), ("symbol", "Symbol file", 160)):
            self.ft.heading(c, text=t); self.ft.column(c, width=w)
        self.ft.pack(fill="both", expand=True, padx=6, pady=6)
        for t in self.S["fixture_types"]:
            self.ft.insert("", "end", values=(t["name"], t["match"], t["symbol"]))
        b = ttk.Frame(f); b.pack(fill="x", padx=6)
        for txt, cmd in (("Add", self.ft_add), ("Edit", self.ft_edit), ("Delete", self.ft_del),
                         ("Pick symbol from PDF...", self.pick_symbol), ("Edit JB position...", self.edit_jb)):
            ttk.Button(b, text=txt, command=cmd).pack(side="left", padx=3, pady=4)
        ttk.Label(f, text="A type is recognised when its text is found in the old tag (e.g. 'LD17.1-'). Longer texts are tried first.",
                  wraplength=700).pack(anchor="w", padx=8, pady=2)

    def symbol_files(self):
        return settings.symbol_names()

    def type_dialog(self, vals=("", "", "")):
        d = tk.Toplevel(self); d.title("Fixture type"); d.transient(self); d.grab_set()
        vs = [tk.StringVar(value=v) for v in vals]
        for r, (lab, v) in enumerate(zip(("Type name", "Found in old-tag text", "Symbol file"), vs)):
            ttk.Label(d, text=lab).grid(row=r, column=0, padx=8, pady=4, sticky="w")
            if r == 2:
                ttk.Combobox(d, textvariable=v, values=self.symbol_files(), width=30).grid(row=r, column=1, padx=8)
            else:
                ttk.Entry(d, textvariable=v, width=33).grid(row=r, column=1, padx=8)
        res = []
        def ok():
            res.extend(v.get().strip() for v in vs); d.destroy()
        ttk.Button(d, text="OK", command=ok).grid(row=3, column=1, sticky="e", padx=8, pady=8)
        self.wait_window(d)
        return res

    def ft_add(self):
        r = self.type_dialog()
        if r and r[0]:
            self.ft.insert("", "end", values=(r[0], r[1], r[2] or r[0]))

    def ft_edit(self):
        s = self.ft.selection()
        if s:
            r = self.type_dialog(self.ft.item(s[0], "values"))
            if r and r[0]:
                self.ft.item(s[0], values=(r[0], r[1], r[2]))

    def ft_del(self):
        for s in self.ft.selection():
            self.ft.delete(s)

    def edit_jb(self):
        s = self.ft.selection()
        if not s:
            return messagebox.showinfo("Settings", "Select a fixture type first.")
        name = self.ft.set(s[0], "symbol")
        sym = settings.load_symbol(name)
        if not sym:
            return messagebox.showinfo("Settings", f"Symbol file '{name}' not found.")
        d = tk.Toplevel(self); d.title("JB position (symbol units)"); d.transient(self); d.grab_set()
        vs = [tk.StringVar(value=str(round(x, 3))) for x in sym["jb"]]
        for r, (lab, v) in enumerate(zip(("JB centre x", "JB centre y (down is +)", "JB size"), vs)):
            ttk.Label(d, text=lab).grid(row=r, column=0, padx=8, pady=4, sticky="w")
            ttk.Entry(d, textvariable=v, width=12).grid(row=r, column=1, padx=8)
        def ok():
            sym["jb"] = [float(v.get()) for v in vs]; settings.save_symbol(sym); d.destroy()
        ttk.Button(d, text="Save", command=ok).grid(row=3, column=1, padx=8, pady=8)

    def pick_symbol(self):
        if not self.app.pdf_path:
            return messagebox.showinfo("Settings", "Open a PDF in the main window first.")
        PickDialog(self)

    # ---- cable sizes
    def build_cable_tab(self, nb):
        f = ttk.Frame(nb); nb.add(f, text="Cable sizes")
        self.cab = ttk.Treeview(f, columns=("key", "size"), show="headings", height=12)
        self.cab.heading("key", text="PANEL/CIRCUIT  (or 'default')"); self.cab.heading("size", text="Cable size")
        self.cab.column("key", width=220); self.cab.column("size", width=300)
        self.cab.pack(fill="both", expand=True, padx=6, pady=6)
        for k, v in self.S["cable_sizes"].items():
            self.cab.insert("", "end", values=(k, v))
        b = ttk.Frame(f); b.pack(fill="x", padx=6)
        ttk.Button(b, text="Add circuits found in PDF", command=self.cab_fill).pack(side="left", padx=3, pady=4)
        ttk.Button(b, text="Edit size", command=self.cab_edit).pack(side="left", padx=3)
        ttk.Button(b, text="Delete", command=lambda: [self.cab.delete(s) for s in self.cab.selection()]).pack(side="left", padx=3)

    def cab_fill(self):
        have = {self.cab.set(i, "key") for i in self.cab.get_children()}
        if self.app.built:
            for k in self.app.built["circuits"]:
                key = f"{k[0]}/{k[1]}"
                if key not in have:
                    self.cab.insert("", "end", values=(key, self.cab.set(self.cab.get_children()[0], "size") if self.cab.get_children() else ""))

    def cab_edit(self):
        s = self.cab.selection()
        if not s:
            return
        d = tk.Toplevel(self); d.title("Cable size"); d.transient(self); d.grab_set()
        v = tk.StringVar(value=self.cab.set(s[0], "size"))
        ttk.Label(d, text=self.cab.set(s[0], "key")).grid(row=0, column=0, padx=8, pady=6)
        ttk.Entry(d, textvariable=v, width=30).grid(row=0, column=1, padx=8)
        def ok():
            self.cab.set(s[0], "size", v.get()); d.destroy()
        ttk.Button(d, text="OK", command=ok).grid(row=1, column=1, pady=8)


class PickDialog(tk.Toplevel):
    """Click a symbol on the drawing; its vector drawing is saved as a symbol file."""
    LOW, HIGH = 30, 720

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Pick symbol - step 1: click near the symbol")
        self.geometry("1100x800")
        S = parent.app.S
        self.S = S
        self.page = pdfplumber.open(parent.app.pdf_path).pages[int(S["page"])]
        self.canvas = ScrollCanvas(self); self.canvas.pack(fill="both", expand=True)
        self.status = ttk.Label(self, text="Click roughly on the symbol you want to copy."); self.status.pack(fill="x")
        self.stage = 1
        self.canvas.show(pil_to_photo(self.page.to_image(resolution=self.LOW).original))
        self.canvas.c.bind("<Button-1>", self.click)

    def click(self, e):
        c = self.canvas.c
        x, y = c.canvasx(e.x), c.canvasy(e.y)
        if self.stage == 1:
            z = self.LOW / 72.0
            cx, cy = x / z, y / z
            half = 40
            self.box = (max(cx - half, 0), max(cy - half, 0), min(cx + half, self.page.width), min(cy + half, self.page.height))
            im = self.page.crop(self.box).to_image(resolution=self.HIGH).original
            self.canvas.show(pil_to_photo(im))
            self.stage = 2
            self.title("Pick symbol - step 2: click the centre of the symbol")
            self.status.config(text="Now click exactly on the symbol.")
        else:
            z = self.HIGH / 72.0
            cx, cy = self.box[0] + x / z, self.box[1] + y / z
            sym = core.extract_symbol(self.page, cx, cy, self.S)
            if not sym:
                return messagebox.showinfo("Pick symbol", "No drawing found there. Try again.")
            from tkinter import simpledialog
            name = simpledialog.askstring("Symbol name", "Name for this symbol (e.g. LD18):", parent=self)
            if not name:
                return
            sym["name"] = name.strip()
            settings.save_symbol(sym)
            if messagebox.askyesno("Pick symbol", f"Saved symbol '{sym['name']}'. Add it as a fixture type?", parent=self):
                m = simpledialog.askstring("Fixture type", "Text found in the old tag for this type (e.g. 'LD18-'):", parent=self)
                self.parent.ft.insert("", "end", values=(sym["name"], m or "", sym["name"]))
            self.destroy()


if __name__ == "__main__":
    App().mainloop()
