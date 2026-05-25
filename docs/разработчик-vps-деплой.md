# Деплой бота на VPS — инструкция для разработчика

## Сценарий

Заказчик создаёт VPS и передаёт вам SSH-доступ. Вы разворачиваете бота удалённо.
На VPS ngrok не нужен — сервер сам доступен из интернета.

---

## Что попросить у заказчика

| Что | Где взять |
|---|---|
| IP-адрес VPS и пароль root | Письмо от хостинга после создания сервера |
| Токен MAX-бота | dev.max.ru → создать бота |
| Токен Яндекс.Диска | oauth.yandex.ru (инструкция в файле разработчик-локальный-перенос.md) |
| Домен или субдомен | Купить у регистратора, или бесплатно на duckdns.org |
| Файл номенклатуры | Excel-файл с товарами |
| Подпись.png, Печать.png | Изображения для КП |

> Если домена нет — зарегистрировать бесплатный субдомен на duckdns.org:
> зайти, выбрать имя (например `company-kp`), указать IP сервера.
> Получится адрес вида `company-kp.duckdns.org`.

---

## Изменения в коде перед деплоем

В `main.py` нужно убрать ngrok и сделать URL вебхука фиксированным.
В `config.py` добавить переменную `WEBHOOK_URL`.
В `.env` добавить `WEBHOOK_URL=https://ваш-домен.com/webhook` и убрать `NGROK_AUTH_TOKEN`.

Сообщите разработчику (себе) когда будете готовы — правки занимают ~5 минут.

---

## Шаг 1. Подключиться к серверу

```powershell
ssh root@IP_АДРЕС_СЕРВЕРА
```

Ввести пароль из письма хостинга.

---

## Шаг 2. Установить зависимости на сервере

```bash
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx unzip
```

---

## Шаг 3. Загрузить код на сервер

**Вариант А — через git (если репозиторий на GitHub):**
```bash
git clone https://github.com/ваш-репо/kp-bot.git /opt/kp-bot
```

**Вариант Б — загрузить архив (с локального компьютера в отдельном терминале):**
```powershell
scp kp-bot.zip root@IP_АДРЕС:/opt/
```
Затем на сервере:
```bash
cd /opt && unzip kp-bot.zip -d kp-bot
```

---

## Шаг 4. Загрузить изображения на сервер

С локального компьютера:
```powershell
scp "Подпись.png" "Печать.png" root@IP_АДРЕС:/opt/kp-bot/
```

---

## Шаг 5. Настроить Python-окружение

```bash
cd /opt/kp-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Шаг 6. Создать .env

```bash
nano /opt/kp-bot/.env
```

Вставить (Ctrl+Shift+V):
```
MAX_BOT_TOKEN=токен_заказчика
YANDEX_DISK_TOKEN=токен_яндекс_диска

YANDEX_DISK_TEMPLATE_PATH=/КП/template.xlsx
YANDEX_DISK_NOMENCLATURE_PATH=/КП/nomenclature.xlsx
YANDEX_DISK_GENERATED_FOLDER=/КП/generated

DATABASE_PATH=/opt/kp-bot/bot.db
WEBHOOK_URL=https://ваш-домен.com/webhook
PORT=8000
```

Сохранить: Ctrl+O, Enter, выйти: Ctrl+X.

---

## Шаг 7. Настроить nginx и HTTPS

Создать конфиг:
```bash
nano /etc/nginx/sites-available/kp-bot
```

Вставить (заменить домен):
```nginx
server {
    listen 80;
    server_name ваш-домен.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Включить и получить SSL-сертификат:
```bash
ln -s /etc/nginx/sites-available/kp-bot /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d ваш-домен.com
```

Certbot попросит email — ввести любой рабочий адрес. Сертификат выдаётся автоматически.

---

## Шаг 8. Настроить автозапуск

```bash
nano /etc/systemd/system/kp-bot.service
```

Вставить:
```ini
[Unit]
Description=KP Bot
After=network.target

[Service]
User=root
WorkingDirectory=/opt/kp-bot
ExecStart=/opt/kp-bot/venv/bin/python main.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Включить и запустить:
```bash
systemctl daemon-reload
systemctl enable kp-bot
systemctl start kp-bot
```

Проверить:
```bash
systemctl status kp-bot
```

Должно быть `Active: active (running)`.

---

## Шаг 9. Проверить и передать

1. Отправить тестовую заявку в MAX — убедиться, что КП приходит
2. Проверить, что файл появился на Яндекс.Диске заказчика
3. Передать заказчику файл `заказчик-vps-управление.md`
4. Попросить заказчика сменить пароль от сервера в личном кабинете хостинга
