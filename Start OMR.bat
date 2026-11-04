@echo off
rem Double-click to open the OMR designer and evaluator in your browser.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 app\server.py) else (python app\server.py)
if errorlevel 1 (
  echo.
  echo Could not start. Python 3.10+ is needed: https://www.python.org/downloads/
  pause
)
