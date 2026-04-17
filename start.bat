@echo off
REM Windows one-click launcher. Creates venv on first run, installs deps, launches dashboard.
setlocal
cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv || goto :error
)

call .venv\Scripts\activate.bat || goto :error

echo Installing/updating dependencies...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || goto :error

python scripts\setup.py || goto :error

echo.
echo Launching dashboard at http://localhost:8501
streamlit run frontend\dashboard.py
goto :eof

:error
echo.
echo Setup failed. Check the output above.
pause
exit /b 1
