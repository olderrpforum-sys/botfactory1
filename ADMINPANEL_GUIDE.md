# BotFactory Admin Panel — VPS Guide (Ubuntu 24.04)

## 1) Что делаем
- Поднимаем админ‑панель `adminpanel.py` на VPS.
- Храним коды доступа, пользователей и компьютеры в SQLite.
- Клиентский модуль `adminapp.py` подключается к API и проверяет коды.

## 2) Подключение к VPS (самый первый шаг)
1. Откройте терминал на своем ПК.
2. Подключитесь по SSH (замените `root`, если у вас другой пользователь):
```bash
ssh root@155.212.168.79
```
3. Если спросит про ключ/пароль — введите пароль от VPS.

## 3) Подготовка VPS
В Ubuntu 24.04 используется Python 3.12, поэтому ставим пакет `python3` и `python3-venv`.
```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nginx
```

## 4) Установка проекта
Если у вас нет репозитория на сервере, сначала загрузите файлы.
Проще всего — залить репозиторий через `git clone`:
```bash
cd /opt
sudo git clone <ВАШ_РЕПО> botfactory1
cd botfactory1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Если нужно **просто установить зависимости из `requirements.txt`** (и виртуальное окружение уже создано):
```bash
cd /opt/botfactory1
source .venv/bin/activate
pip install -r requirements.txt
```

Если Git не используете — можно загрузить папку с файлами через SFTP (например, FileZilla)
в `/opt/botfactory1`, а затем выполнить команды с `cd /opt/botfactory1`.

## 5) Настройка переменных окружения
Создайте файл `/opt/botfactory1/.env`:
```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=СЛОЖНЫЙ_ПАРОЛЬ
ADMINPANEL_PORT=8000
ADMIN_ALLOWED_IPS=ВАШ_IP_ИЛИ_СПИСОК_ЧЕРЕЗ_ЗАПЯТУЮ
```

**Важно:** замените `СЛОЖНЫЙ_ПАРОЛЬ` на свой длинный пароль.
Если хотите, чтобы админ‑панель была доступна только вам, укажите свой IP в `ADMIN_ALLOWED_IPS`
(например: `ADMIN_ALLOWED_IPS=46.163.138.129`).

Не нужно менять `adminpanel.py` вручную. Достаточно указать `ADMIN_ALLOWED_IPS` в `.env`
в виде строки (без фигурных скобок).

## 6) Systemd сервис
Создайте `/etc/systemd/system/adminpanel.service`:
```
[Unit]
Description=BotFactory Admin Panel
After=network.target

[Service]
User=root
WorkingDirectory=/opt/botfactory1
EnvironmentFile=/opt/botfactory1/.env
ExecStart=/opt/botfactory1/.venv/bin/python adminpanel.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Запуск:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now adminpanel.service
sudo systemctl status adminpanel.service
```

Если статус `active (running)` — всё ок.

## 7) Настройка Nginx
Создайте `/etc/nginx/sites-available/adminpanel`:
```
server {
    listen 80;
    server_name 155.212.168.79;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/adminpanel /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 8) Проверка
```bash
curl http://155.212.168.79/health
```

Если ответ `{"status":"ok"}` — сервер работает.

## 9) Пример работы с API
Логин:
```bash
curl -X POST http://155.212.168.79/admin/login \
  -H "Content-Type: application/json" \
  -d '{"login":"admin","password":"СЛОЖНЫЙ_ПАРОЛЬ"}'
```

Создать код:
```bash
curl -X POST http://155.212.168.79/admin/codes \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"issued_to":"user1","expires_in_days":30}'
```

Посмотреть коды:
```bash
curl -X GET http://155.212.168.79/admin/codes \
  -H "Authorization: Bearer <TOKEN>"
```

## 10) Быстрая генерация одноразового кода на сервере
Код одноразовый: его можно активировать только на одном компьютере.

Команда для генерации нового кода прямо в консоли VPS:
```bash
cd /opt/botfactory1
source .venv/bin/activate
python adminpanel.py generate-code --days 30 --issued-to user1
```

Вывод будет таким:
```
{"code":"XXXX","expires_at":"2026-02-15T20:52:23+00:00"}
```

## 11) Интеграция клиента
В `adminapp.py` пропишите URL:
```
ADMIN_API_BASE = "http://155.212.168.79"
```

Запуск проверки кода:
```bash
python adminapp.py
```

## 12) Бэкапы базы
SQLite база по умолчанию: `/opt/botfactory1/adminpanel.db`
```bash
cp /opt/botfactory1/adminpanel.db /opt/botfactory1/adminpanel.db.bak
```

## 13) Частые ошибки (новичкам)
1. **Не открывается сайт** — проверьте, что сервис запущен:
   ```bash
   sudo systemctl status adminpanel.service
   ```
2. **Nginx ругается** — проверьте конфиг:
   ```bash
   sudo nginx -t
   ```
3. **Неверный пароль** — замените `ADMIN_PASSWORD` в `.env` и перезапустите:
   ```bash
   sudo systemctl restart adminpanel.service
   ```
