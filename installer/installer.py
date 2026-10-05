# -*- coding: utf-8 -*-
"""Installateur de Stickaru (Windows, sans droits administrateur).

Copie Stickaru.exe dans %LOCALAPPDATA%\\Programs\\Stickaru, crée les raccourcis
(menu Démarrer + Bureau) et déclare le programme dans « Applications installées ».
Construit avec PyInstaller : voir build_installer.bat.
"""
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

NOM = "Stickaru"
VERSION = "1.1.0"


def ressource(nom):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nom)


DOSSIER = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Programs", NOM)

PS_RACCOURCIS = r"""
param([string]$Dossier)
$w = New-Object -ComObject WScript.Shell
$menu = [Environment]::GetFolderPath('Programs')
$bureau = [Environment]::GetFolderPath('Desktop')
foreach ($p in @("$menu\Stickaru.lnk", "$bureau\Stickaru.lnk")) {
    $l = $w.CreateShortcut($p)
    $l.TargetPath = "$Dossier\Stickaru.exe"
    $l.WorkingDirectory = $Dossier
    $l.IconLocation = "$Dossier\chat.ico"
    $l.Save()
}
$u = $w.CreateShortcut("$menu\Desinstaller Stickaru.lnk")
$u.TargetPath = "$Dossier\uninstall.cmd"
$u.IconLocation = "$Dossier\chat.ico"
$u.Save()
"""

UNINSTALL_CMD = r"""@echo off
setlocal
set "D=%LOCALAPPDATA%\Programs\Stickaru"
taskkill /IM Stickaru.exe /F >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$m=[Environment]::GetFolderPath('Programs');$b=[Environment]::GetFolderPath('Desktop');foreach($f in @(\"$m\Stickaru.lnk\",\"$b\Stickaru.lnk\",\"$m\Desinstaller Stickaru.lnk\")){Remove-Item -LiteralPath $f -ErrorAction SilentlyContinue}"
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Stickaru" /f >nul 2>&1
cd /d "%TEMP%"
start "" /min cmd /c "ping -n 3 127.0.0.1 >nul & rd /s /q "%D%""
echo Stickaru a ete desinstalle.
endlocal
"""


def declarer_desinstallation():
    try:
        import winreg
        cle = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Stickaru")
        for nom, val in (("DisplayName", NOM), ("DisplayVersion", VERSION),
                         ("Publisher", "Paquereauman"), ("InstallLocation", DOSSIER),
                         ("DisplayIcon", os.path.join(DOSSIER, "chat.ico")),
                         ("UninstallString", 'cmd /c "%s"' % os.path.join(DOSSIER, "uninstall.cmd"))):
            winreg.SetValueEx(cle, nom, 0, winreg.REG_SZ, val)
        winreg.SetValueEx(cle, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(cle)
    except Exception:
        pass


def installer():
    os.makedirs(DOSSIER, exist_ok=True)
    subprocess.run(["taskkill", "/IM", "Stickaru.exe", "/F"], capture_output=True,
                   creationflags=0x08000000)
    for f in ("Stickaru.exe", "chat.ico"):
        shutil.copy2(ressource(f), os.path.join(DOSSIER, f))
    with open(os.path.join(DOSSIER, "uninstall.cmd"), "w", encoding="ascii", newline="\r\n") as fh:
        fh.write(UNINSTALL_CMD)
    ps1 = os.path.join(DOSSIER, "raccourcis.ps1")
    with open(ps1, "w", encoding="utf-8-sig") as fh:
        fh.write(PS_RACCOURCIS)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1,
                    "-Dossier", DOSSIER], capture_output=True, creationflags=0x08000000)
    try:
        os.remove(ps1)
    except OSError:
        pass
    declarer_desinstallation()


def main():
    racine = tk.Tk()
    racine.withdraw()
    if not messagebox.askyesno(
            "Installation de %s" % NOM,
            "Installer %s %s pour ton compte Windows ?\n\nDossier : %s\n"
            "Des raccourcis seront créés dans le menu Démarrer et sur le Bureau." % (NOM, VERSION, DOSSIER)):
        return
    try:
        installer()
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("Installation de %s" % NOM, "L'installation a échoué :\n%s" % e)
        return
    messagebox.showinfo("Installation de %s" % NOM, "%s est installé. Il va se lancer." % NOM)
    subprocess.Popen([os.path.join(DOSSIER, "Stickaru.exe")], cwd=DOSSIER)


if __name__ == "__main__":
    main()
