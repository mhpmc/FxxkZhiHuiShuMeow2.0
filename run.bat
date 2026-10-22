@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

rem Pick a Python 3.11+ interpreter: python first, then the py launcher.
set "PYRUN="
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 set "PYRUN=python"
if not defined PYRUN (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYRUN=py -3"
)
if not defined PYRUN (
    echo 喵?！需要 Python 3.11 或更新版本喵～
    echo 请先安装 Python：https://www.python.org/downloads/
    echo 安装时记得勾选 "Add Python to PATH" 喵～
    pause
    exit /b 1
)

rem Playwright is the only runtime dependency. Install it on first run.
%PYRUN% -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo 喵…还没装 playwright，正在自动下载依赖喵～
    %PYRUN% -m pip --version >nul 2>&1
    if errorlevel 1 (
        echo 喵…pip 也不在，先补一个 pip 喵～
        %PYRUN% -m ensurepip --upgrade
    )
    %PYRUN% -m pip install --disable-pip-version-check -r "script\requirements.txt"
    if errorlevel 1 (
        echo 喵…直接安装失败了，改到用户目录再试一次喵～
        %PYRUN% -m pip install --user --disable-pip-version-check -r "script\requirements.txt"
    )
    %PYRUN% -c "import playwright" >nul 2>&1
    if errorlevel 1 (
        echo 喵…依赖还是没装上，请检查网络后重试喵～
        echo 也可以手动运行：
        echo     %PYRUN% -m pip install -r script\requirements.txt
        pause
        exit /b 1
    )
    echo 喵~ 依赖装好啦，开始刷课喵～
)

rem No arguments: open the Tkinter UI. With arguments: keep the old CLI.
if "%~1"=="" (
    %PYRUN% "script\ui.py"
) else (
    %PYRUN% "script\run.py" %*
)
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
    echo.
    echo 喵…本次退出码 %CODE%，结果在 script\output 里喵～
    pause
)
exit /b %CODE%
