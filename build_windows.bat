@echo off
REM Build a standalone Windows .exe of the GAME_MASTER decoder GUI.
REM Requires Python 3.8+ on PATH. Run from this folder: build_windows.bat

echo === Creating virtual environment ===
python -m venv .venv || goto :err
call .venv\Scripts\activate.bat || goto :err

echo === Installing PyInstaller ===
python -m pip install --upgrade pip
python -m pip install pyinstaller || goto :err

echo === Building executable ===
pyinstaller --noconfirm pogodecode.spec || goto :err

echo.
echo === Done ===
echo Your app is here:  dist\PoGoGameMasterDecoder.exe
echo.
pause
exit /b 0

:err
echo.
echo BUILD FAILED. See the messages above.
pause
exit /b 1
