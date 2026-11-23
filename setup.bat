@echo off
setlocal
cd /d "%~dp0"

py -3 -c "import sys, struct; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 15) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 (
    echo Python 3.12 a 3.15 64 bits et le lanceur Python sont requis.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "delims=" %%v in ('py -3 -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))"') do set "PYTHON_VERSION=%%v"

if exist ".venv" if not exist ".venv\Scripts\python.exe" (
    echo L'environnement .venv est incomplet. Renommez-le puis relancez ce fichier.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto error
)

".venv\Scripts\python.exe" -c "import sys, struct; sys.exit(0 if sys.version_info[:2] == tuple(map(int, '%PYTHON_VERSION%'.split('.'))) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo L'environnement .venv n'utilise pas Python %PYTHON_VERSION% 64 bits.
    echo Renommez .venv, puis relancez ce fichier.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error

echo Lancement de l'application Streamlit...
".venv\Scripts\python.exe" -m streamlit run app.py
if errorlevel 1 goto error
pause
exit /b 0

:error
echo Une erreur s'est produite. Consultez les messages ci-dessus.
pause
exit /b 1