import os
import json
import csv
import re
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import NetworkError, RetryAfter, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

# Токен бота из переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
# ID админов (можно указать несколько через запятую)
ADMIN_CHAT_IDS_STR = os.getenv("ADMIN_CHAT_ID", "")
ADMIN_CHAT_IDS = [id.strip() for id in ADMIN_CHAT_IDS_STR.split(",") if id.strip()] if ADMIN_CHAT_IDS_STR else []
# Ники админов: с @ или без (например: @admin1, admin2)
ADMIN_USERNAMES_STR = os.getenv("ADMIN_USERNAMES", "")
ADMIN_USERNAMES = [u.strip().lstrip("@").lower() for u in ADMIN_USERNAMES_STR.split(",") if u.strip()] if ADMIN_USERNAMES_STR else []

# Состояния пользователей
user_states = {}

# Файл для сохранения данных пользователей
DATA_FILE = Path("user_data.json")
RAFFLE_NUMBERS_FILE = Path("raffle_numbers.json")
HELP_REQUESTS_FILE = Path("help_requests.json")

# Пути к изображениям
IMAGES_DIR = Path("images")
WELCOME_IMAGE = IMAGES_DIR / "welcome.png"

# Загружаем существующие данные
if DATA_FILE.exists():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        user_data = json.load(f)
else:
    user_data = {}

# Загружаем запросы на помощь
if HELP_REQUESTS_FILE.exists():
    with open(HELP_REQUESTS_FILE, "r", encoding="utf-8") as f:
        help_requests = json.load(f)
else:
    help_requests = []

# Загружаем существующие номера розыгрыша
if RAFFLE_NUMBERS_FILE.exists():
    with open(RAFFLE_NUMBERS_FILE, "r", encoding="utf-8") as f:
        raffle_data = json.load(f)
        # Проверяем формат файла (старый или новый)
        if isinstance(raffle_data, dict) and "numbers" in raffle_data:
            # Новый формат
            raffle_numbers = raffle_data.get("numbers", {})
            next_raffle_number = raffle_data.get("next_number", 1)
        else:
            # Старый формат - конвертируем
            raffle_numbers = raffle_data
            # Вычисляем следующий номер на основе максимального существующего
            if raffle_numbers:
                max_number = max(raffle_numbers.values())
                next_raffle_number = max_number + 1 if max_number < 1000 else 1001
            else:
                next_raffle_number = 1
else:
    raffle_numbers = {}
    next_raffle_number = 1

# Определение заданий
QUESTIONS = [
    {
        "number": 1,
        "text": (
            "*Первое задание:*\n\n"
            "Познакомься с любым участником митапа и узнай, есть ли у вас общие интересы и хобби.\n"
            "Пришли боту: «Я и (имя участника) вместе любим …»."
        ),
        "keywords": ["я", "и", "вместе", "любим"],
    },
    {
        "number": 2,
        "text": (
            "*Второе задание:*\n\n"
            "Закончи фразу «На митапе PRO AI я хочу ….» и пришли в этот чат.\n"
            "Это могут быть твои ожидания от митапа."
        ),
        "keywords": ["хочу", "митап", "pro", "ai"],
    },
    {
        "number": 3,
        "text": (
            "*Третье задание:*\n\n"
            "Расшифруй ИИ-понятия по эмодзи:\n"
            "🤖🧠\n"
            "🚗📖\n"
            "🧠📶\n"
            "🖥️👁️\n\n"
            "Пришли ответы в сообщении.\n"
            "Можно использовать разные разделители: запятые, точки, переносы строк, тире.\n"
            "Порядок ответов не важен.\n"
        ),
        "keywords": ["искусственный", "интеллект", "машинное", "обучение", "нейросеть", "нейрон", "компьютерное", "зрение", "vision"],
        "correct_answer": (
            "Правильные ответы на 3 задание:\n"
            "🤖🧠 - искусственный интеллект\n"
            "🚗📖 - машинное обучение\n"
            "🧠📶 - нейросеть\n"
            "🖥️👁️ - компьютерное зрение"
        ),
    },
    {
        "number": 4,
        "text": (
            "*Четвертое задание:*\n\n"
            "Передай привет любому участнику митапа, с которым успел пообщаться или познакомиться.\n"
            "Напиши свое послание."
        ),
        "keywords": ["привет", "здравствуй", "приветствую"],
    },
    {
        "number": 5,
        "text": (
            "*Пятое задание:*\n\n"
            "Узнай у любого человека на митапе, каким неочевидным навыком он гордится\n"
            "(например: «умеет собирать кубик-рубик за минуту»).\n"
            "Пришли сюда имя человека и его навык."
        ),
        "keywords": ["умеет", "навык", "гордится", "может"],
    },
    {
        "number": 6,
        "text": (
            "*Шестое задание:*\n\n"
            "У тебя есть любое приложение нейросети? Самое время воспользоваться!\n"
            "Спроси у твоей любимой нейросети, что такое «Аугментация данных в ИИ простыми словами?»,\n"
            "и отправь короткий ответ."
        ),
        "keywords": [],
    },
]


def escape_markdown_v2(text: str) -> str:
    """Экранирует специальные символы для MarkdownV2"""
    # Важно: экранируем в правильном порядке, чтобы не экранировать уже экранированные символы
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!', ':', ',']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def to_cp1251_safe(text: str) -> str:
    """
    Преобразует строку в вид, безопасный для сохранения в cp1251:
    все неподдерживаемые символы (эмодзи и пр.) заменяются на '?'.
    """
    try:
        return text.encode("cp1251", errors="replace").decode("cp1251")
    except Exception:
        # Запасной вариант: выкидываем неподдерживаемые символы
        return text.encode("cp1251", errors="ignore").decode("cp1251")


def save_user_data():
    """Сохраняет данные пользователей в файл"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(user_data, f, ensure_ascii=False, indent=2)


def save_help_requests():
    """Сохраняет запросы на помощь в файл"""
    with open(HELP_REQUESTS_FILE, "w", encoding="utf-8") as f:
        json.dump(help_requests, f, ensure_ascii=False, indent=2)




def save_raffle_numbers():
    """Сохраняет номера розыгрыша в файл"""
    global next_raffle_number
    raffle_data = {
        "numbers": raffle_numbers,
        "next_number": next_raffle_number
    }
    with open(RAFFLE_NUMBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(raffle_data, f, ensure_ascii=False, indent=2)


def save_raffle_table():
    """Автоматически сохраняет таблицу участников розыгрыша в CSV для Excel"""
    # Собираем данные участников с номерами
    participants = []
    for user_id, data in user_data.items():
        raffle_number = data.get("raffle_number")
        if raffle_number is not None:
            participants.append({
                "number": raffle_number,
                "username": data.get("username", ""),
                "full_name": data.get("full_name", ""),
                "handle": data.get("handle", ""),
                "completed_at": data.get("completed_at", "")
            })
    
    if not participants:
        return
    
    # Сортируем по номеру розыгрыша
    participants.sort(key=lambda x: x["number"])
    
    # Сохраняем TXT файл: Имя, ник, @username, номер (в удобном для чтения виде)
    txt_file = Path("raffle_table.txt")
    with open(txt_file, "w", encoding="cp1251") as f_txt:
        for p in participants:
            full_name = p["full_name"] or p["username"] or "Не указано"
            username = p["username"] or "Не указан"
            handle = p.get("handle") or ""
            handle_str = f"@{handle}" if handle else ""
            # cp1251-safe варианты (чтобы не было иероглифов при открытии в Windows/мобильных редакторах)
            full_name_safe = to_cp1251_safe(full_name)
            username_safe = to_cp1251_safe(username)
            handle_safe = to_cp1251_safe(handle_str)
            # Имя;отображаемое имя;@username;номер
            f_txt.write(f"{full_name_safe};{username_safe};{handle_safe};{p['number']}\n")
    
    # Сохраняем CSV файл (UTF‑8 с BOM + ';' — чтобы Excel корректно показывал русский текст)
    csv_file = Path("raffle_table.csv")
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        # Без заголовков, @username;отображаемое имя;номер
        for p in participants:
            time_str = ""
            if p["completed_at"]:
                try:
                    dt = datetime.fromisoformat(p["completed_at"])
                    time_str = dt.strftime("%H:%M:%S")
                except:
                    time_str = p["completed_at"][:8] if len(p["completed_at"]) > 8 else p["completed_at"]
            handle = p.get("handle") or ""
            handle_str = f"@{handle}" if handle else ""
            username = p["username"] or "Не указан"
            # В CSV оставляем оригинальные строки, UTF‑8 их поддерживает полностью
            # Записываем: @username;Имя;Номер
            writer.writerow([handle_str, username, p["number"]])


def generate_raffle_number() -> int:
    """Генерирует последовательный номер для розыгрыша от 1 до 1000"""
    global next_raffle_number
    
    if next_raffle_number > 1000:
        raise ValueError("Достигнут лимит номеров розыгрыша (1000)")
    
    number = next_raffle_number
    next_raffle_number += 1
    return number


def validate_answer(message_text: str, question: dict, question_index: int) -> tuple[bool, str]:
    """
    Валидирует ответ пользователя
    Возвращает (is_valid, error_message)
    """
    text_lower = message_text.lower().strip()
    
    # Минимальная длина ответа
    if len(text_lower) < 5:
        return False, "Ваш ответ слишком короткий. Пожалуйста, напишите более развернутый ответ."
    
    # Специфичная валидация для каждого задания
    if question_index == 0:  # Задание 1: "Я и ... вместе любим ..."
        required_words = ["я", "и"]
        if not all(word in text_lower for word in required_words):
            return False, (
                "Пожалуйста, используйте формат: «Я и [имя] вместе любим [интерес]».\n"
                "Например: «Я и Мария вместе любим pro ai."
            )
        if "вместе" not in text_lower and "любим" not in text_lower:
            return False, "В вашем ответе должно быть упоминание общего интереса с другим участником."
    
    elif question_index == 1:  # Задание 2: "На митапе Pro AI я хочу ..."
        if len(text_lower) < 10:
            return False, "Пожалуйста, напишите более подробно о ваших ожиданиях от митапа."
    
    elif question_index == 2:  # Задание 3 обрабатывается отдельно в handle_message
        return True, ""
    
    elif question_index == 3:  # Задание 4: Привет участнику
        greeting_words = ["привет", "здравствуй", "приветствую", "здравствуйте", "hi", "hello"]
        if not any(word in text_lower for word in greeting_words):
            return False, (
                "Это задание про передачу привета участнику митапа.\n"
                "Напишите приветственное сообщение для кого-то из участников."
            )
    
    elif question_index == 4:  # Задание 5: Навык участника
        # Только базовая проверка на минимальную длину ответа
        if len(text_lower) < 10:
            return False, "Пожалуйста, напишите чуть подробнее про участника и его навык."
    
    elif question_index == 5:  # Задание 6: Аугментация данных
        if len(text_lower) < 10:
            return False, "Пожалуйста, пришлите более развернутый ответ."
    
    return True, ""


def check_emoji_answer(text_lower: str) -> tuple[bool, list[str]]:
    """
    Проверяет ответ на задание с эмодзи.
    Возвращает (is_correct, missing_concepts)
    """
    # Правильные ответы на эмодзи с различными вариантами написания
    correct_answers = {
        "🤖🧠": [
            "искусственный интеллект", "ии", "ai", "artificial intelligence",
            "искусственныйинтеллект"
        ],
        "🚗📖": [
            "машинное обучение", "ml", "machine learning",
            "машинноеобучение", "мл"
        ],
        "🧠📶": [
            "нейросеть", "нейронная сеть", "neural network", "nn",
            "нейросети", "нейронные сети"
        ],
        "🖥️👁️": [
            "компьютерное зрение", "cv", "computer vision",
            "компьютерноезрение"
        ]
    }
    
    # Нормализуем текст: убираем лишние пробелы, приводим к нижнему регистру
    # Заменяем различные разделители на пробелы для унификации
    normalized_text = re.sub(r'[,\-\.;:\n\r\t]+', ' ', text_lower)
    normalized_text = " ".join(normalized_text.split())
    
    # Проверяем наличие всех правильных ответов
    found_answers = {}
    for emoji, variants in correct_answers.items():
        found = False
        for variant in variants:
            if variant in normalized_text:
                found_answers[emoji] = True
                found = True
                break
        if not found:
            found_answers[emoji] = False
    
    if all(found_answers.values()):
        return True, []
    
    # Возвращаем список тех эмодзи, которые пользователь ещё не расшифровал
    missing_emojis: list[str] = [emoji for emoji, ok in found_answers.items() if not ok]
    return False, missing_emojis


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    username = user.first_name if user.first_name else user.username
    user_id = user.id
    
    # Проверяем, начал ли пользователь уже квест
    if str(user_id) in user_data and user_data[str(user_id)].get("started_at"):
        # Пользователь уже начал квест
        raffle_number = user_data[str(user_id)].get("raffle_number")
        
        if raffle_number:
            # Квест уже завершен
            await update.message.reply_text(
                f"*Вы уже завершили квест\\!*\n\n"
                f"Ваш номер для розыгрыша: *{raffle_number}*",
                parse_mode="MarkdownV2"
            )
        else:
            # Квест начат, но не завершен
            # Восстанавливаем состояние из сохраненных данных
            saved_answers = user_data[str(user_id)].get("answers", {})
            if saved_answers:
                # Определяем текущее задание по количеству ответов
                current_question_index = len(saved_answers)
                if current_question_index < len(QUESTIONS):
                    question_text = QUESTIONS[current_question_index]["text"]
                    await update.message.reply_text(
                        f"*Вы уже начали проходить квест\\.*\n\n"
                        f"Текущее задание:\n\n{escape_markdown_v2(question_text)}\n\n"
                        "Продолжайте выполнять задания\\.",
                        parse_mode="MarkdownV2"
                    )
                else:
                    await update.message.reply_text(
                        "*Вы уже начали проходить квест\\.*\n\n"
                        "Продолжайте выполнять задания\\.",
                        parse_mode="MarkdownV2"
                    )
            else:
                await update.message.reply_text(
                    "*Вы уже начали проходить квест\\.*\n\n"
                    "Продолжайте выполнять задания\\.",
                    parse_mode="MarkdownV2"
                )
        return
    
    # Инициализируем данные пользователя
    user_data[str(user_id)] = {
        # "username" — отображаемое имя (первое имя или то, что видит пользователь)
        "username": username,
        "full_name": user.full_name,
        "telegram_id": user_id,
        # "handle" — телеграм‑ник без '@' (User.username)
        "handle": user.username or "",
        "started_at": datetime.now().isoformat(),
        "answers": {},
        "raffle_number": None,
        "completed_at": None
    }
    save_user_data()
    
    # Сбрасываем состояние пользователя
    user_states[user_id] = {
        "stage": "welcome", 
        "current_question": 0,
        "answers": {}
    }
    
    welcome_text = (
        f"*Привет, {username}*\\!\n\n"
        "*Рады видеть тебя на Большом митапе PRO AI\\!*\n\n"
        "Для участия в розыгрыше призов присоединяйся к квесту\\. "
        "Это займет всего несколько минут, и ты сможешь выиграть крутые призы\\!"
    )
    
    keyboard = [
        [InlineKeyboardButton("Присоединиться к квесту", callback_data="join_quest")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем фото с приветствием, если файл существует
    if WELCOME_IMAGE.exists():
        with open(WELCOME_IMAGE, "rb") as photo:
            await update.message.reply_photo(
                photo=InputFile(photo),
                caption=welcome_text,
                parse_mode="MarkdownV2",
                reply_markup=reply_markup
            )
    else:
        # Если фото нет, отправляем только текст
        await update.message.reply_text(
            welcome_text,
            parse_mode="MarkdownV2",
            reply_markup=reply_markup
        )


async def join_quest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Присоединиться'"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Обновляем состояние
    user_states[user_id] = {
        "stage": "quest_info", 
        "current_question": 0,
        "answers": user_data[str(user_id)].get("answers", {})
    }
    
    quest_info_text = (
        "*Что нужно сделать:*\n\n"
        "• Выполнить *6 заданий* в боте\n"
        "• Успеть до *17:30*\n"
        "• В конце квеста ты получишь *номер для участия в розыгрыше*\n\n"
        "Задания нетрудные: предстоит приятный нетворкинг и пару интересных задачек\\!\n\n"
        "*Готов начать?*"
    )
    
    keyboard = [
        [InlineKeyboardButton("Приступить к заданию 1", callback_data="start_quest")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # После приветственного сообщения отправляем отдельный пост с условиями квеста
    await query.message.reply_text(
        quest_info_text,
        parse_mode="MarkdownV2",
        reply_markup=reply_markup
    )


async def start_quest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало квеста - показываем первое задание"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Обновляем состояние
    user_states[user_id] = {
        "stage": "answering", 
        "current_question": 0,
        "answers": user_data[str(user_id)].get("answers", {})
    }
    
    # Отправляем первое задание отдельным сообщением
    question = QUESTIONS[0]
    await query.message.reply_text(
        question["text"],
        parse_mode="Markdown"
    )
    
    # Обновляем состояние
    user_states[user_id]["current_question"] = 0
    user_states[user_id]["stage"] = "answering"


async def show_question(query, user_id: int, question_index: int):
    """Показывает задание пользователю"""
    question = QUESTIONS[question_index]
    question_text = question["text"]
    
    # Проверяем, есть ли фото в сообщении
    try:
        if query.message.photo:
            # Если сообщение с фото, редактируем подпись
            await query.edit_message_caption(
                caption=question_text,
                parse_mode="Markdown",
                reply_markup=None
            )
        else:
            # Если обычное текстовое сообщение, редактируем текст
            await query.edit_message_text(
                question_text,
                parse_mode="Markdown"
            )
    except Exception as e:
        # Если не удалось отредактировать, отправляем новое сообщение
        await query.message.reply_text(
            question_text,
            parse_mode="Markdown"
        )
    
    # Обновляем состояние
    user_states[user_id]["current_question"] = question_index
    user_states[user_id]["stage"] = "answering"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Проверяем, есть ли состояние у пользователя
    if user_id not in user_states:
        await update.message.reply_text(
            "Для начала работы с ботом используйте команду /start"
        )
        return
    
    state = user_states[user_id]
    
    # Если пользователь не в процессе ответа на вопрос
    if state["stage"] != "answering":
        # Пользователь уже прошёл квест
        if state.get("stage") == "completed":
            user_id_str = str(user_id)
            raffle_number = (
                state.get("raffle_number")
                or user_data.get(user_id_str, {}).get("raffle_number")
            )
            if raffle_number:
                msg = (
                    "Квест завершён, ты молодец!\n\n"
                    "Все 6 заданий выполнены\n\n"
                    f"Твой номер для розыгрыша: {raffle_number}\n\n"
                )
            else:
                msg = (
                    "Квест уже завершён.\n\n"
                    "Все 6 заданий выполнены.\n\n"
                )
            await update.message.reply_text(msg)
        else:
            # Пользователь ещё не начал квест или в другом состоянии
            await update.message.reply_text(
                "Для участия в квесте используй команду /start."
            )
        return
    
    current_question_index = state["current_question"]
    question = QUESTIONS[current_question_index]
    
    # Отдельная логика для задания с эмодзи (3-е задание, индекс 2)
    if current_question_index == 2:
        text_lower = message_text.lower().strip()
        is_correct, missing = check_emoji_answer(text_lower)
        
        # Считаем попытки пользователя для этого задания
        attempts = state.get("emoji_attempts", 0)
        
        if is_correct:
            # Сбросим счётчик попыток и похвалим за точные ответы
            state["emoji_attempts"] = 0
            await update.message.reply_text(
                "Круто! Все ответы совпали, ты отлично справился.",
                # без разметки, чтобы не ловить ошибок Markdown
            )
        else:
            attempts += 1
            state["emoji_attempts"] = attempts
            
            if attempts == 1:
                # Первая ошибочная попытка: показываем по эмодзи, что ещё не расшифровано
                if missing:
                    missing_list = ", ".join(missing)
                    msg = (
                        "Не все ответы совпали.\n\n"
                        f"Ты пока не расшифровал: {missing_list}.\n\n"
                        "Попробуй ещё раз — у тебя есть ещё одна попытка."
                    )
                else:
                    msg = (
                        "Ответ пока не выглядит полным.\n\n"
                        "Попробуй ещё раз — у тебя есть ещё одна попытка."
                    )
                await update.message.reply_text(msg)
                return
            else:
                # Вторая (и далее) неудачная попытка — показываем правильные ответы и идём дальше
                state["emoji_attempts"] = 0
                correct_text = question.get("correct_answer")
                if correct_text:
                    await update.message.reply_text(
                        "Немного не совпало, но ничего страшного — это было непростое задание.\n\n"
                        "Вот правильные ответы:"
                    )
                    await update.message.reply_text(correct_text)
                # Считаем ответ принятым и переходим к следующему заданию ниже (как обычно)
    
    # Общая валидация для остальных заданий
    if current_question_index != 2:
        is_valid, error_message = validate_answer(message_text, question, current_question_index)
        
        if not is_valid:
            # Экранируем специальные символы для MarkdownV2
            escaped_error = escape_markdown_v2(error_message)
            await update.message.reply_text(
                f"{escaped_error}\n\n"
                "Попробуйте еще раз\\!",
                parse_mode="MarkdownV2"
            )
            return
    
    # Сохраняем ответ пользователя
    user_id_str = str(user_id)
    if "answers" not in user_states[user_id]:
        user_states[user_id]["answers"] = {}
    
    user_states[user_id]["answers"][current_question_index] = {
        "answer": message_text,
        "timestamp": datetime.now().isoformat()
    }
    
    # Сохраняем в файл
    if user_id_str not in user_data:
        user_obj = update.effective_user
        user_data[user_id_str] = {
            "username": user_obj.first_name or user_obj.username,
            "full_name": user_obj.full_name,
            "telegram_id": user_id,
            "handle": user_obj.username or "",
            "started_at": datetime.now().isoformat(),
            "answers": {},
            "raffle_number": None,
            "completed_at": None
        }
    
    user_data[user_id_str]["answers"][current_question_index] = {
        "answer": message_text,
        "timestamp": datetime.now().isoformat()
    }
    save_user_data()
    
    # Фиксируем ответ с дружелюбным сообщением
    question_number = current_question_index + 1
    await update.message.reply_text(
        f"*Отлично\\!* Ответ на задание *{question_number}* зафиксирован\\.\n\n"
        "Переходим дальше\\.\\.\\.",
        parse_mode="MarkdownV2"
    )
    
    # Переходим к следующему заданию или завершаем квест
    next_question_index = current_question_index + 1
    
    if next_question_index < len(QUESTIONS):
        # Показываем следующее задание
        await asyncio.sleep(1)
        question_text = QUESTIONS[next_question_index]["text"]
        await update.message.reply_text(
            question_text,
            parse_mode="Markdown"
        )
        user_states[user_id]["current_question"] = next_question_index
    else:
        # Квест завершен
        await complete_quest(update, user_id)


async def complete_quest(update: Update, user_id: int):
    """Завершение квеста"""
    user_id_str = str(user_id)
    
    # Генерируем номер для розыгрыша
    raffle_number = generate_raffle_number()
    raffle_numbers[user_id_str] = raffle_number
    save_raffle_numbers()
    
    # Сохраняем номер в данные пользователя
    user_data[user_id_str]["raffle_number"] = raffle_number
    user_data[user_id_str]["completed_at"] = datetime.now().isoformat()
    save_user_data()
    
    # Автоматически обновляем таблицу участников
    save_raffle_table()
    
    # Обновляем состояние
    user_states[user_id]["stage"] = "completed"
    user_states[user_id]["raffle_number"] = raffle_number
    
    completion_text = (
        "*Квест пройден, поздравляем\\!*\n\n"
        f"*Твой номер для розыгрыша: {raffle_number}*\n\n"
        "Сохрани этот номер\\! Он понадобится для участия в розыгрыше призов\\.\n\n"
        "Розыгрыш состоится в *18:00* на основной сцене\\.\n\n"
        "Жди объявления результатов\\! Удачи\\!"
    )
    
    # Отправляем только текст без фото
    await update.message.reply_text(
        completion_text,
        parse_mode="MarkdownV2"
    )


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для получения выгрузки участников (только для организаторов)"""
    user_id = update.effective_user.id
    username = (update.effective_user.username or "").lower()

    # Проверяем: админ по ID или по нику (@username / username)
    is_admin_by_id = ADMIN_CHAT_IDS and str(user_id) in ADMIN_CHAT_IDS
    is_admin_by_username = ADMIN_USERNAMES and username in ADMIN_USERNAMES

    if not (is_admin_by_id or is_admin_by_username):
        await update.message.reply_text(
            "Доступ запрещен\\. Эта команда доступна только организаторам\\.",
            parse_mode="MarkdownV2"
        )
        return
    
    # Генерируем выгрузку
    save_raffle_table()
    
    # Отправляем CSV и TXT
    try:
        files_sent = False

        if Path("raffle_table.csv").exists():
            with open("raffle_table.csv", "rb") as csv_file:
                await update.message.reply_document(
                    document=InputFile(csv_file, filename="raffle_table.csv"),
                    caption="*Выгрузка участников розыгрыша \\(CSV\\)*",
                    parse_mode="MarkdownV2"
                )
            files_sent = True

        if Path("raffle_table.txt").exists():
            with open("raffle_table.txt", "rb") as txt_file:
                await update.message.reply_document(
                    document=InputFile(txt_file, filename="raffle_table.txt"),
                    caption="Имя;ник;номер в розыгрыше",
                )
            files_sent = True

        if not files_sent:
            await update.message.reply_text(
                "*Выгрузка пока недоступна\\.*\n\n"
                "Участников еще нет\\.",
                parse_mode="MarkdownV2"
            )
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка при отправке выгрузки: {escape_markdown_v2(str(e))}",
            parse_mode="MarkdownV2"
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок для всего приложения"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    # Обработка сетевых ошибок
    if isinstance(context.error, NetworkError):
        logger.warning(f"Сетевая ошибка: {context.error}. Бот продолжит работу...")
        return
    
    # Обработка ошибок таймаута
    if isinstance(context.error, TimedOut):
        logger.warning(f"Таймаут запроса: {context.error}. Бот продолжит работу...")
        return
    
    # Обработка ошибок rate limit
    if isinstance(context.error, RetryAfter):
        logger.warning(f"Превышен лимит запросов. Ожидание {context.error.retry_after} секунд...")
        await asyncio.sleep(context.error.retry_after)
        return


def main():
    """Основная функция запуска бота"""
    if not BOT_TOKEN:
        print("Ошибка: BOT_TOKEN не установлен в переменных окружения!")
        print("Создайте файл .env и добавьте туда BOT_TOKEN=ваш_токен")
        return
    
    # Создаем приложение с настройками для обработки сетевых ошибок
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем глобальный обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CallbackQueryHandler(join_quest, pattern="^join_quest$"))
    application.add_handler(CallbackQueryHandler(start_quest, pattern="^start_quest$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    print("Бот запущен...")
    
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,  # Игнорировать старые обновления при перезапуске
            close_loop=False  # Не закрывать event loop при ошибках
        )
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка при работе бота: {e}", exc_info=True)
        print(f"\nОшибка: {e}")
        print("\nВозможные причины:")
        print("1. Проблемы с интернет-соединением")
        print("2. Блокировка Telegram API (может потребоваться VPN/прокси)")
        print("3. Неверный BOT_TOKEN")
        print("\nПопробуйте перезапустить бота через несколько секунд.")


if __name__ == "__main__":
    main()
