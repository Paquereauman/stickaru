@echo off
rem Construit Stickaru-Setup.exe (installateur). Prerequis : pip install pyinstaller, et Stickaru.exe + chat.ico dans le dossier parent.
cd /d %~dp0
copy /Y ..\Stickaru.exe . >nul
copy /Y ..\chat.ico . >nul
python -m PyInstaller --onefile --noconsole --icon chat.ico --name Stickaru-Setup --add-data "Stickaru.exe;." --add-data "chat.ico;." installer.py
echo Installateur : dist\Stickaru-Setup.exe
