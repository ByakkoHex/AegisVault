@echo off
title Password Manager - Serwer Synchronizacji
color 0A

echo.
echo  =========================================
echo   Password Manager - Serwer Sync
echo   http://localhost:8000
echo   Dokumentacja: http://localhost:8000/docs
echo  =========================================
echo.

:: Przejdz do folderu gdzie jest skrypt
cd /d "%~dp0"

:: Sprawdz czy Python jest zainstalowany
py --version >nul 2>&1
if errorlevel 1 (
    echo  [BLAD] Python nie jest zainstalowany lub nie jest w PATH!
    pause
    exit /b 1
)

:: Sprawdz czy istnieje plik serwera
if not exist "server\main.py" (
    echo  [BLAD] Nie znaleziono pliku server\main.py
    echo  Upewnij sie ze uruchamiasz skrypt z glownego folderu projektu!
    pause
    exit /b 1
)

:: Sprawdz czy uvicorn jest zainstalowany
py -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo  [INFO] Instaluje brakujace zaleznosci...
    pip install fastapi uvicorn python-jose[cryptography] bcrypt sqlalchemy
    echo.
)

echo  [OK] Uruchamiam serwer...
echo  Zatrzymaj serwer przez: Ctrl+C
echo.

py -m uvicorn server.main:app --reload --port 8000

echo.
echo  Serwer zatrzymany.
pause
