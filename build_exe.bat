@echo off
setlocal

py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python 3.11 не найден. Установи Python 3.11 x64 и попробуй снова.
  pause
  exit /b 1
)

echo Installing deps...
py -3.11 -m pip install -r requirements.txt
py -3.11 -m pip install pyinstaller

echo Building EXE...
py -3.11 -m PyInstaller ^
  --noconsole ^
  --name TelegramBotFactoryApp ^
  --clean ^
  --noconfirm ^
  --collect-all PyQt6 ^
  --collect-all telethon ^
  app.py

echo Done.
echo Output: dist\TelegramBotFactoryApp\TelegramBotFactoryApp.exe
pause
