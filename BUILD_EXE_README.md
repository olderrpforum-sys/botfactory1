# Сборка EXE (Windows 10/11)

PyQt6 не поддерживает Python 3.13, поэтому используем Python 3.11 (x64).

## 1) Установи Python 3.11 (x64)
Отметь **Add Python to PATH**.

Проверь:
```bat
py -3.11 --version
```

## 2) Установи зависимости + PyInstaller
```bat
py -3.11 -m pip install -r requirements.txt
py -3.11 -m pip install pyinstaller
```

## 3) Собери EXE
```bat
build_exe.bat
```

Готовый файл:
`dist\TelegramBotFactoryApp\TelegramBotFactoryApp.exe`
