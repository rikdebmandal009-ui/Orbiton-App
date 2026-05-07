@echo off
title Nitrosamine IMS — Starting...
color 0A

echo.
echo  =====================================================
echo   Nitrosamine Inventory Intelligence System
echo   Starting local server...
echo  =====================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found!
    echo  Please install Python 3.11 from python.org
    echo  Make sure to tick "Add Python to PATH"
    pause
    exit /b
)

:: Install dependencies silently if needed
echo  Checking dependencies...
pip install flask pandas openpyxl scikit-learn numpy -q --disable-pip-version-check

:: Copy Excel files to data folder if present in same directory
if exist "Nitrosamine_general_orbiton.xlsx" (
    copy /Y "Nitrosamine_general_orbiton.xlsx" "data\nitrosamines.xlsx" >nul
    echo  Loaded: Nitrosamine_general_orbiton.xlsx
)
if exist "Raw_materials_for_Nitrosamines_orbiton-2.xlsx" (
    copy /Y "Raw_materials_for_Nitrosamines_orbiton-2.xlsx" "data\raw_materials.xlsx" >nul
    echo  Loaded: Raw_materials_for_Nitrosamines_orbiton-2.xlsx
)

echo.
echo  Starting dashboard at http://localhost:5050
echo  Your browser will open automatically...
echo  Press Ctrl+C to stop the system.
echo.

python app.py

pause
