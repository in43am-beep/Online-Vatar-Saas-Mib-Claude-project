@echo off
title MIB Avatar Production System
cd /d "d:\Avatar Automation - local and Saas -2026\Online-Vatar-Saas-Mib-Claude-project\avatar-production-mib"
echo Starting MIB Avatar Production System...
python run_app.py
if errorlevel 1 (
    echo.
    echo ERROR: App crashed. See error above.
    pause
)
