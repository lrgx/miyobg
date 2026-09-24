@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "TARGET=%~1"
if not defined TARGET set "TARGET=x64"
if /I "%TARGET%"=="x86" (
    echo [ERROR] PySide6 / Qt 6 has no official Windows x86 32-bit package.
    echo         This PySide6 application cannot be packaged as x86 with supported dependencies.
    exit /b 2
)
if /I not "%TARGET%"=="x64" if /I not "%TARGET%"=="arm64" (
    echo Usage: build_nuitka.cmd x64^|arm64 [path-to-target-architecture-python.exe]
    exit /b 2
)

set "PYTHON_EXE=%~2"
if not defined PYTHON_EXE set "PYTHON_EXE=python"
set "VSDEVCMD=D:\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat"
if not exist "%VSDEVCMD%" (
    echo [ERROR] Visual Studio developer prompt not found: "%VSDEVCMD%"
    exit /b 2
)
if not exist "%~dp0logo.ico" (
    echo [ERROR] logo.ico not found next to this script.
    exit /b 2
)

"%PYTHON_EXE%" -c "import os,platform,struct,sys; target=os.environ['TARGET'].lower(); machine=platform.machine().lower(); bits=struct.calcsize('P')*8; ok=bits==64 and machine in ({'x64':('amd64','x86_64'),'arm64':('arm64','aarch64')}[target]); print('Python:',sys.version.split()[0],machine,str(bits)+'-bit'); sys.exit(0 if ok else 1)"
if errorlevel 1 (
    echo [ERROR] Python architecture does not match %TARGET%. Use a native %TARGET% Python installation.
    exit /b 2
)
"%PYTHON_EXE%" -c "import nuitka,PySide6; print('PySide6:',PySide6.__version__)"
if errorlevel 1 (
    echo [ERROR] Install Nuitka and PySide6 into the selected Python environment first.
    exit /b 2
)

call "%VSDEVCMD%" -arch=%TARGET% >nul
if errorlevel 1 (
    echo [ERROR] Failed to activate the %TARGET% Visual Studio toolchain.
    exit /b 2
)

set "UCRT_INCLUDE=%WindowsSdkDir%Include\%WindowsSDKVersion%ucrt"
set "UCRT_LIB=%WindowsSdkDir%Lib\%WindowsSDKVersion%ucrt\%TARGET%"
if not exist "%UCRT_INCLUDE%\ctype.h" (
    echo [ERROR] Windows SDK UCRT headers are missing. Install the Universal CRT component.
    exit /b 2
)
if not exist "%UCRT_LIB%\ucrt.lib" (
    echo [ERROR] Windows SDK UCRT library for %TARGET% is missing.
    exit /b 2
)
set "INCLUDE=%INCLUDE%;%UCRT_INCLUDE%"
set "LIB=%LIB%;%UCRT_LIB%"
"%PYTHON_EXE%" -m nuitka ^
    --mode=onefile ^
    --enable-plugin=pyside6 ^
    --include-qt-plugins=multimedia ^
    --windows-console-mode=disable ^
    --windows-icon-from-ico="%~dp0logo.ico" ^
    --include-data-files="%~dp0logo.ico=logo.ico" ^
    --msvc=latest ^
    --output-dir="%~dp0dist\%TARGET%" ^
    --output-filename="miyobg-%TARGET%.exe" ^
    "%~dp0mihoyo_wallpaper.py"
if errorlevel 1 exit /b 1

echo [OK] Built "%~dp0dist\%TARGET%\miyobg-%TARGET%.exe"
exit /b 0
