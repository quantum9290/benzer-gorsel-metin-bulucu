@echo off
cd /d "%~dp0"

rem 1. Sanal ortam varsa aktif et ve calistir
if exist venv (
    echo Sanal ortam aktif ediliyor...
    call venv\Scripts\activate
    echo Sunucu baslatiliyor...
    start "Benzer Görsel ve Metin Bulucu" cmd /k "python -m uvicorn main:app --host 0.0.0.0 --port 8000"
    goto launch_browser
)

rem 2. Sanal ortam yoksa, py launcher ile uvicorn'u kontrol et
py -c "import uvicorn" >nul 2>&1
if %errorlevel% equ 0 (
    echo Sistemdeki Python ile sunucu baslatiliyor...
    start "Benzer Görsel ve Metin Bulucu" cmd /k "py -m uvicorn main:app --host 0.0.0.0 --port 8000"
    goto launch_browser
)

rem 3. py launcher ile uvicorn bulunamadiysa, venv olusturup kur
echo Sanal ortam veya uvicorn bulunamadi. venv olusturuluyor...
py -m venv venv
if %errorlevel% neq 0 (
    echo Sanal ortam olusturulamadi. Lutfen Python yuklu oldugundan emin olun.
    pause
    exit /b 1
)

echo Bagimliliklar kuruluyor...
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo Sunucu baslatiliyor...
start "Benzer Görsel ve Metin Bulucu" cmd /k "python -m uvicorn main:app --host 0.0.0.0 --port 8000"

:launch_browser
timeout /t 5 /nobreak > nul
start http://localhost:8000
exit
