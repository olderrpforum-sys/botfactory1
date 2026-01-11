# Telegram BotFactory v7 (stable)

## Разделы
- **Ручное создание** — всё вручную: имя/username, setuserpic, токены.
- **Автоматическое создание** — полностью автоматом:
  - вводишь имена через `/` (пример: `name/name2/name3`)
  - имя бота: `ОРИГ С ТТ❤️<name>`
  - username: `<name>_bot`, если invalid/taken/unavailable → `<name>_1bot` … `<name>_5bot`
  - распределение по аккаунтам по кругу **без повторов**
  - **лимит строго 2 бота на аккаунт за 1 запуск** (1 запуск = 1 круг)
- **Статистика** — типы (“хомяки”) с процентом + автоподсчёт количества ботов по `tokens.csv`.

## Файлы
- `accounts_tg.txt` — `phone:password:api_id:api_hash` (если 2FA пароля нет — `UNKOWN`)
- `tokens.txt` — только токены (по одному в строке)
- `tokens.csv` — phone, username, token, type, mode
- `stats.json` — типы и проценты
- `sessions/` — сессии Telegram

## Установка
```bash
pip install -r requirements.txt
```

## Запуск
```bash
python app.py
```

## EXE (Windows)
Сборка через Python 3.11: `build_exe.bat` (см. BUILD_EXE_README.md)
