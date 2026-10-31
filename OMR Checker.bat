@echo off
rem Double-click to start OMR Checker. The first start sets up a private Python
rem environment in .venv and installs the requirements; later starts open the
rem window straight away.
setlocal
cd /d "%~dp0"
set "VENV=%~dp0.venv"
set "PY=%VENV%\Scripts\python.exe"

if exist "%PY%" goto :deps
echo First start: setting up OMR Checker. This takes a few minutes...
where py >nul 2>nul
if %errorlevel%==0 (py -3 -m venv "%VENV%") else (python -m venv "%VENV%")
if not exist "%PY%" goto :nopython

:deps
"%PY%" -c "import webview, quickjs, cv2, flask, waitress, pymupdf, pandas, screeninfo" >nul 2>nul
if %errorlevel%==0 goto :run
echo Installing requirements...
"%PY%" -m pip install --disable-pip-version-check -q -r scans_to_csv\requirements.txt -r app\requirements.txt opencv-contrib-python
if errorlevel 1 goto :installfailed

:run
start "" "%VENV%\Scripts\pythonw.exe" "%~dp0app\desktop.py"
exit /b 0

:nopython
echo.
echo Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH", then double-click this file again.
pause
exit /b 1

:installfailed
echo.
echo Installing the requirements failed; see the messages above.
echo Check the internet connection and double-click this file again.
pause
exit /b 1
