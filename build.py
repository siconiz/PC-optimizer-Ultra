"""Builds dist/PCOptimizer (one-folder app) with PyInstaller. Run on Windows: python build.py"""
import os, shutil
import customtkinter
import PyInstaller.__main__
import tools_hash

tools_hash.update()  # widget fingerprints in core/addons.py must match widgets/*.py
ctk_dir = os.path.dirname(customtkinter.__file__)

PyInstaller.__main__.run([
    "main.py",
    "--noconfirm",
    "--onedir",          # customtkinter data files do not work with --onefile
    "--windowed",
    "--uac-admin",
    "--name", "PCOptimizer",
    "--add-data", f"{ctk_dir}{os.pathsep}customtkinter/",
    "--collect-all", "pythonnet",   # Python.Runtime.dll for LibreHardwareMonitorLib
    "--collect-all", "clr_loader",
    "--hidden-import", "clr",
    "--collect-submodules", "ui",          # pages are imported on first visit (importlib), so list them all
    "--collect-submodules", "core",
    "--collect-submodules", "pycaw",       # used by the downloadable audio widget and the overlay
    "--collect-submodules", "comtypes",
    "--exclude-module", "win32ui",  # MFC UI module, not used
    "--exclude-module", "unittest", "--exclude-module", "pydoc", "--exclude-module", "lib2to3",
    "--exclude-module", "comtypes.test",
    "--optimize", "1",              # smaller, slightly faster start-up
    "--icon", "assets/icon.ico",
    "--add-data", f"assets{os.pathsep}assets",
    "--add-data", f"widgets{os.pathsep}widgets",   # offline copy of the downloadable widgets (a few KB)
])
if os.path.isdir("tools"):  # PresentMon, LibreHardwareMonitorLib, PawnIO installer
    shutil.copytree("tools", os.path.join("dist", "PCOptimizer", "tools"), dirs_exist_ok=True)
