@echo off
rem Builds ONE file: dist\LoopDiagramBuilder.exe  (needs Python 3.10+ for Windows; the exe itself needs nothing installed)
py -m pip install -r requirements.txt pyinstaller
py -m PyInstaller --noconfirm --onefile --windowed --name LoopDiagramBuilder --collect-all pdfplumber --collect-all pdfminer --collect-all pypdfium2 --add-data "symbols;symbols" --add-data "settings.json;." app.py
echo.
echo Done. Single file: dist\LoopDiagramBuilder.exe
pause
