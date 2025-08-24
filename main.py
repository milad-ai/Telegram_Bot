import os
import re
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, Document
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from sqlalchemy import create_engine, text
from flask import Flask
from threading import Thread

# ==================== تنظیمات ====================
TOKEN = os.environ.get("BOT_TOKEN")
DB_URI = os.environ.get("DB_URI")

if not TOKEN or not DB_URI:
    raise ValueError("BOT_TOKEN and DB_URI must be set!")

engine = create_engine(DB_URI)

majors = [["علوم کامپیوتر"], ["آمار"]]
hw_numbers = [["3"]]

user_state = {}

welcome_text = (
    "🎓 ربات درس پایگاه داده 🎓\n\n"
    "خوش آمدید! این ربات برای دانشجویان ترم ۱۴۰۴–۱۴۰۵ "
    "دانشگاه شهید بهشتی، دانشکده ریاضی طراحی شده است.\n\n"
    "می‌توانید رشته خود را انتخاب کنید، شماره تمرین را وارد کنید، "
    "و فایل یا متن SQL خود را ارسال کنید تا بررسی و تصحیح شود.\n\n"
    "📚 موفق باشید!"
)

# ==================== توابع ====================
def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    update.message.reply_text(welcome_text)
    user_state[chat_id] = "waiting_major"
    reply_markup = ReplyKeyboardMarkup(majors, one_time_keyboard=True)
    update.message.reply_text("لطفاً رشته خود را انتخاب کنید:", reply_markup=reply_markup)

def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text

    if user_state.get(chat_id) == "waiting_major":
        if text in ["علوم کامپیوتر", "آمار"]:
            context.user_data["major"] = text
            user_state[chat_id] = "waiting_hw"
            reply_markup = ReplyKeyboardMarkup(hw_numbers, one_time_keyboard=True)
            update.message.reply_text("رشته انتخاب شد. شماره تمرین را انتخاب کنید:", reply_markup=reply_markup)
        else:
            update.message.reply_text("لطفاً یکی از گزینه‌های منو را انتخاب کنید.")

    elif user_state.get(chat_id) == "waiting_hw":
        if text in ["3"]:
            context.user_data["hw"] = text
            user_state[chat_id] = "waiting_student_info"
            update.message.reply_text(
                "نام و شماره دانشجویی خود را با کاما وارد کنید (مثلاً: علی رضایی, 12345):",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            update.message.reply_text("لطفاً شماره تمرین معتبر انتخاب کنید.")

    elif user_state.get(chat_id) == "waiting_student_info":
        try:
            parts = text.split(",")
            if len(parts) != 2:
                raise ValueError("فرمت اشتباه")
            name = parts[0].strip()
            student_id = parts[1].strip()
            context.user_data["name"] = name
            context.user_data["student_id"] = student_id
            user_state[chat_id] = "waiting_sql"
            update.message.reply_text("لطفاً SQL خود را ارسال کنید یا فایل .sql بفرستید.")
        except Exception:
            update.message.reply_text("فرمت نامعتبر. لطفاً از فرمت: نام فارسی, شماره دانشجویی استفاده کنید.")

    elif user_state.get(chat_id) == "waiting_sql":
        sql_text = text
        process_sql(update, context, sql_text)

# ==================== دریافت فایل SQL ====================
def handle_document(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    if user_state.get(chat_id) != "waiting_sql":
        update.message.reply_text("لطفاً مراحل را از /start دنبال کنید.")
        return

    document: Document = update.message.document
    if not document.file_name.endswith(".sql"):
        update.message.reply_text("لطفاً یک فایل معتبر .sql ارسال کنید.")
        return

    file = document.get_file()
    sql_text = file.download_as_bytearray().decode("utf-8")
    process_sql(update, context, sql_text)

# ==================== پردازش SQL ====================
def process_sql(update: Update, context: CallbackContext, sql_text: str):
    chat_id = update.message.chat_id

    queries = re.split(r"#\s*number\s*\d+", sql_text, flags=re.IGNORECASE)
    queries = [q.strip() for q in queries if q.strip()]

    hw = context.user_data["hw"]
    name = context.user_data["name"]
    student_id = context.user_data["student_id"]

    correct_count = 0

    with engine.connect() as conn:
        for i, student_query in enumerate(queries):
            try:
                student_rows = conn.execute(text(student_query)).fetchall()
                reference_table = f"hw{hw}_q{i+1}_reference"
                reference_rows = conn.execute(text(f"SELECT * FROM {reference_table}")).fetchall()
                if set(student_rows) == set(reference_rows):
                    correct_count += 1
            except Exception as e:
                print(f"Error executing query {i+1}: {e}")

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS student_results (
                student_id TEXT,
                name TEXT,
                hw TEXT,
                correct_count INT
            )
        """))

        conn.execute(
            text("INSERT INTO student_results (student_id, name, hw, correct_count) VALUES (:student_id, :name, :hw, :correct_count)"),
            {"student_id": student_id, "name": name, "hw": hw, "correct_count": correct_count}
        )

    update.message.reply_text(f"تصحیح انجام شد! {correct_count}/{len(queries)} Query درست است.")
    user_state[chat_id] = None

# ==================== راه‌اندازی ربات ====================
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
dp.add_handler(MessageHandler(Filters.document, handle_document))
updater.start_polling()

# ==================== وب سرور Flask برای Keep Alive ====================
app = Flask('')
@app.route('/')
def home():
    return "ربات تلگرام فعال است ✅"

def run():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

Thread(target=run).start()
updater.idle()
