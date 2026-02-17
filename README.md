# Telegram бот для квеста Pro AI

Квест на митапе: 6 заданий, розыгрыш, выгрузка для организаторов.

## Установка

1. Установите зависимости:

```bash
pip install -r requirements.txt
```

2. Создайте `.env` на основе `.env.example`, укажите токен бота от [@BotFather](https://t.me/BotFather):

```
BOT_TOKEN=ваш_токен_здесь
```

При необходимости добавьте `ADMIN_CHAT_ID` и/или `ADMIN_USERNAMES` для команды `/export`.

3. (Опционально) Положите в папку `images/` файл `welcome.png` для приветственного сообщения.

## Запуск

```bash
python bot.py
```
