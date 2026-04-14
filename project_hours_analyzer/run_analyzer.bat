@echo off
setlocal

echo Project Hours Analyzer
echo ======================
echo.
echo Select an estimation preset:
echo   1. Conservative  (multiplier: 0.75 - tighter session gaps)
echo   2. Moderate      (multiplier: 1.00 - balanced)
echo   3. Generous      (multiplier: 1.50 - wider session gaps)
echo.
set /p CHOICE="Enter 1, 2, or 3 [default: 1]: "

if "%CHOICE%"=="2" (
    set PRESET=moderate
) else if "%CHOICE%"=="3" (
    set PRESET=generous
) else (
    set PRESET=conservative
)

echo.
echo Running with preset: %PRESET%
echo.

python "%~dp0project_hours_analyzer.py" %PRESET%

endlocal
pause
