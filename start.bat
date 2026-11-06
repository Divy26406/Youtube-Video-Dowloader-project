@echo off
title StreamDrop Pro - YouTube Downloader
cd /d "%~dp0"
echo ========================================================
echo   Starting StreamDrop Pro - YouTube Video & MP3 Downloader
echo ========================================================
echo.
python run.py
if errorlevel 1 (
    echo.
    echo An error occurred while launching StreamDrop.
    echo Press any key to exit.
    pause >nul
)
