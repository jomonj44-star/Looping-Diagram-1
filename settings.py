"""Settings for Loop Diagram Builder. Everything here can be edited in the Settings window
or directly in settings.json."""
import json, os, copy, sys

def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def bundle_dir():
    """folder holding the defaults packed inside a single-file .exe (same as app_dir() when not packed)"""
    return getattr(sys, "_MEIPASS", app_dir())

SETTINGS_FILE = os.path.join(app_dir(), "settings.json")      # your edits are saved next to the .exe
SYMBOL_DIR = os.path.join(app_dir(), "symbols")
BUNDLED_SETTINGS = os.path.join(bundle_dir(), "settings.json")
BUNDLED_SYMBOLS = os.path.join(bundle_dir(), "symbols")

DEFAULTS = {
    "scale": 200,                 # drawing scale 1:scale
    "paper_factor": 1.0,          # 1.0 = PDF plotted at 100 %
    "length_multiplier": 1.0,     # e.g. 1.10 for +10 % route allowance
    "extra_per_span_m": 0.0,      # fixed extra length added to every span (m)
    "long_span_warn_m": 45.0,     # spans longer than this are flagged in Checks
    "verify": {"max_span_m": 100.0, "watt_tolerance": 0.0, "expected_total_w": 0},   # Excel verification limits (0 = off)
    "page": 0,                    # PDF page number (0 = first)
    "annot_subtype": "FreeText",  # annotation type that holds the NEW tags
    "leader_color": [0.0, 0.5, 0.5],   # stroke colour of the leader lines (symbol -> old tag box)
    "match_tol": 12.0,            # max distance (pdf units) from leader end to old tag box
    "text_gap": 4.0,              # characters further apart than this start a new text piece
    "old_tag_regex": r"^\d\dB[NL]L\d\d/",   # first line of an OLD tag
    "tag_regex": r"^(?P<panel>\w+)/(?P<cct>\d+)L(?P<ph>\d)-(?P<no>\d+)(?:/(?P<cct2>\d+)L(?P<ph2>\d)-(?P<no2>\d+))?$",
    "phase_order": ["1", "2", "3"],
    "jb_suffix": "-JB",          # JB tag = fixture tag + suffix
    "jb_label": "JB: ",
    "cable_tag": "{panel}/{cct}-C{n:02d}",   # {panel} {cct} {n} (run number from the panel)
    "cable_sizes": {"default": "5C x 16 sq.mm"},   # also "PANEL/CCT": "3C x 2.5 sq.mm"
    "fixture_types": [
        {"name": "LD17",   "match": "LD17-",   "symbol": "LD17"},
        {"name": "LD17.1", "match": "LD17.1-", "symbol": "LD17.1"},
        {"name": "LD16.1", "match": "LD16.1-", "symbol": "LD16.1"},
        {"name": "LD16.2", "match": "LD16.2-", "symbol": "LD16.2"},
    ],
    "pick": {"radius": 12.0, "max_size": 9.0, "jb_color": [0.5, 0.0, 0.5],
             "ignore_colors": [[0.0, 0.5, 0.0], [0.5], [0.0, 0.5, 0.5], [0.0, 0.0, 1.0]]},
    "project": {"name": "", "drawing_no": "", "client": "", "location": "", "revision": "0", "date": "",
                "prepared": "", "checked": "", "approved": "", "note": ""},
    "out": {
        "bw_symbols": True, "per_row": 5, "dx": 96, "dy": 84, "symbol_scale": 3.6,
        "symbol_inches_per_unit": 0.0,    # common symbol size on every circuit sheet (page inches per drawing unit); 0 = largest that fits
        "paper": "A3", "orientation": "landscape",      # A4 / A3 / A2 / A1 / A0 / Letter / Tabloid / Custom ; landscape / portrait
        "layout_dir": "horizontal",                     # horizontal (rows) / vertical (columns)
        "cover_page": True,
        "page_w_in": 16.54, "page_h_in": 11.69,         # used only when paper = Custom
        "tag_fill": "#a8ff40", "tag_edge": "#e00000", "tag_text": "#001a66",
        "line_color": "#007000", "length_color": "#006000",
        "show_old_tag": True, "show_jb_tag": True, "show_cable_tag": True,
        "title": "LOOPING DIAGRAM", "source_note": "",
    },
}

PAPERS = {"A4": (8.27, 11.69), "A3": (11.69, 16.54), "A2": (16.54, 23.39), "A1": (23.39, 33.11), "A0": (33.11, 46.81),
          "Letter": (8.5, 11.0), "Tabloid": (11.0, 17.0)}      # portrait (width, height) in inches


def page_size(S):
    """(width, height) in inches from Settings -> Output -> Paper / Orientation (Custom uses page_w_in x page_h_in)"""
    O = S["out"]
    p = PAPERS.get(O.get("paper", "A3"))
    if not p:
        return float(O["page_w_in"]), float(O["page_h_in"])
    w, h = p
    return (h, w) if str(O.get("orientation", "landscape")).lower().startswith("l") else (w, h)


def merge(base, new):
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict) and k not in ("cable_sizes",):
            merge(base[k], v)
        else:
            base[k] = v
    return base

def load(path=None):
    s = copy.deepcopy(DEFAULTS)
    p = path or SETTINGS_FILE
    if not os.path.exists(p) and not path:
        p = BUNDLED_SETTINGS
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            merge(s, json.load(f))
    return s

def save(s, path=None):
    with open(path or SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)

def load_symbol(name):
    p = os.path.join(SYMBOL_DIR, name + ".json")
    if not os.path.exists(p):
        p = os.path.join(BUNDLED_SYMBOLS, name + ".json")
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def save_symbol(sym):
    os.makedirs(SYMBOL_DIR, exist_ok=True)
    with open(os.path.join(SYMBOL_DIR, sym["name"] + ".json"), "w", encoding="utf-8") as f:
        json.dump(sym, f)

def symbol_names():
    names = set()
    for d in (SYMBOL_DIR, BUNDLED_SYMBOLS):
        if os.path.isdir(d):
            names |= {os.path.splitext(x)[0] for x in os.listdir(d) if x.endswith(".json")}
    return sorted(names)
