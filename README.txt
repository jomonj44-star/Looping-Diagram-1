LOOP DIAGRAM BUILDER  (Windows)
===============================
Reads a marked-up PDF (old tags in the drawing, NEW tags as red callout comments) and produces:
  - a cover sheet with the overall MTO (fixtures by type, lighting JB, cable length by size),
  - one looping-diagram sheet per panel/circuit (PDF symbols, JB tags, cable tags, lengths at the drawing scale, MTO),
  - an Excel file with the MTO, cable spans (from JB / to JB / cable tag / length) and the old -> new tag list.

RUN (needs Python 3.10+ for Windows, python.org)
  double-click run.bat            (installs the libraries, starts the program)
  or, from a command prompt:      py app.py
  no window / batch use:          py app.py --cli drawing.pdf --out Looping_Diagram.pdf --xlsx MTO.xlsx

MAKE A STAND-ALONE .EXE (so other PCs do not need Python)
  double-click build_exe.bat      ->  dist\LoopDiagramBuilder\LoopDiagramBuilder.exe
  (keep the "symbols" folder and settings.json next to the .exe)

INPUT = EXCEL (Circuiting / Load Balance workbook)
  Open Excel.  Each table (Normal left, Emergency right, one per circuit) is read from the sheets:
    - a POLE starts at every row that has a FIXTURE INSTALLATION TYPE; the rows below it without a type are further
      fixtures on the same pole (tag becomes e.g. 12BNL40/01L1-01/01L2-01)
    - FROM FIXTURE/PANEL decides the loop: poles can branch (two cables leave the same pole)
    - LENGTH = cable length (m) from the FROM pole to this pole; the first pole's length is panel to pole
    - the lengths add up to the total printed under each table (checked); load per phase is calculated from the fixtures
  The sheets show the branching loop, JB tags, cable tags, lengths, MTO (types, JB, cable, load per phase); two cover pages give the overall MTO.
  Layout: poles per row, column width and row spacing are chosen automatically from the measured text size so tags never overlap
          (set "tree_per_row" in settings.json -> out to force a number of poles per row).
  Command line:  py app.py --cli workbook.xlsx --out Looping_Diagram.pdf --xlsx MTO.xlsx
  Checks list Excel problems (FROM not found, empty FROM, PHASES column different from the tag, missing type or length...).

USE
  1. Open PDF.  The tags are read and matched automatically (big drawings can take about a minute).
  2. Pick a sheet in the left list to preview it.  The "Checks" box lists problems
     (duplicate fixtures, gaps, circuit typos, very long spans, tags without a fixture type).
  3. Settings -> change anything -> Save (everything is recalculated).
  4. Export PDF / Export MTO (Excel).

EVERYTHING IS MODIFIABLE  (Settings window, or edit settings.json)
  Drawing & length   scale (1:200), paper factor, length multiplier (e.g. 1.10), extra length per span, long-span warning
  Tags & reading     new-tag pattern, old-tag pattern, phase order, JB suffix (-JB), cable tag format, leader colour, tolerances
  Fixture types      add / rename / delete types; "Found in old-tag text" decides the type (LD17-, LD17.1- ...)
  Symbols            "Pick symbol from PDF": click the symbol on the drawing, it is copied as a vector symbol file
                     (symbols\NAME.json). "Edit JB position" sets which square is the lighting JB.
  Cable sizes        one size per PANEL/CIRCUIT plus a default; used in every MTO table
  Output             poles per row, spacing, symbol size, page size, colours, black & white symbols, show/hide old/JB/cable tags
  Profiles           Save profile as / Load profile for different projects

HOW LENGTHS ARE CALCULATED
  straight-line distance between the symbol positions on the PDF (pdf points -> mm -> x scale) x length multiplier
  + extra per span.  Panel to first fixture is not included (the panel position is not marked on the drawing).

NOTES
  - Tested on the Street_Emergency drawing (122 tags matched, 8 circuits).  Other drawings need the same layout:
    new tags = callout comments, leader lines to the old tag box drawn in the leader colour set in Settings.
  - The fixture order in a circuit is by fixture number then phase (L1, L2, L3).

TAG CHECK (new)
  Button "Tag Check (duplicates)" in the window, or:  python app.py --cli --tagcheck drawing.pdf --out marked.pdf --xlsx list.xlsx
  Works on a PDF whose new tags are plain text (e.g. TAGG UPDATED). It circles on the PDF:
  red = same pole tag on two poles, orange = fixture tag also used on another pole,
  magenta = suspicious tag (stray '-', phase L4, two fixtures from different circuits) and writes the list to Excel.

SINGLE-FILE EXE
  GitHub: upload this folder to a repository, Actions > "Build Windows EXE" > Run workflow, download LoopDiagramBuilder-exe (one file, nothing to install).
  Or on a Windows PC with Python: run build_exe.bat -> dist\LoopDiagramBuilder.exe
  Default symbols/settings are inside the exe; settings you change are saved in settings.json / symbols\ next to the exe.

NEW: PAGE, LAYOUT, PROJECT COVER, EXCEL VERIFICATION
 Settings -> "Page & layout": paper size (A4 A3 A2 A1 A0 Letter Tabloid Custom), orientation (landscape / portrait),
 diagram direction (horizontal / vertical), project cover page on/off, symbol size (0 = largest that fits).
 The symbol scale is the same on every circuit and text never overlaps symbols or lines; the symbols shrink instead.
 Settings -> "Project": project name, drawing no., client, revision, date ... printed on the extra project cover page.
 These apply to diagrams made from the Excel. Diagrams made from a marked-up PDF still use the older A3 landscape layout.
 Tip: A4 portrait works well with 'vertical'; A4 portrait 'horizontal' gives very small symbols.
 Verify Excel (button, or:  python app.py --cli workbook.xlsx --verify --xlsx report.xlsx)
 writes an Excel report: Summary, Issues (missing values, tag / PANEL / CIRCUIT / PHASES mismatches, unknown fixture type,
 duplicate tags, numbering gaps, FROM not found, length and load totals vs the Excel total rows, long spans), Circuit totals.
 Command line: --paper A4 --orientation portrait --layout vertical --no-cover --project "Name" --drawing-no "DWG-1"
