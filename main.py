
import os
import re
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, Document
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from sqlalchemy import create_engine, text
from flask import Flask
from threading import Thread
import jdatetime
from datetime import datetime
import pytz

# ==================== تنظیمات ====================

TOKEN = os.environ.get("BOT_TOKEN")
DB_URI = os.environ.get("DB_URI")

if not TOKEN or not DB_URI:
    raise ValueError("BOT_TOKEN and DB_URI must be set!")

engine = create_engine(DB_URI, pool_pre_ping=True)

hw_numbers = [["3", "4", "5", "6"]]
user_state = {}

welcome_text = (
    "🎓 خوش آمدید به ربات پایگاه داده! 🎓\n\n"
    "✨ این ربات برای درس پایگاه داده دانشجویان در نیم‌سال اول ۱۴۰۵–۱۴۰۴\n"
    "🏛️ دانشگاه شهید بهشتی - دانشکده ریاضی طراحی شده است.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📋 راهنمای استفاده:\n"
    "1️⃣ شماره دانشجویی خود را وارد کنید\n"
    "2️⃣ رمز عبور خود را وارد کنید\n"
    "3️⃣ شماره تمرین را انتخاب کنید (3، 4، 5، 6)\n"
    "4️⃣ کد SQL خود را ارسال کنید (متن یا فایل .sql)\n\n"
    "⚠️ نکات مهم:\n"
    "• قبل از هر سوال حتماً کامنت # number X بگذارید\n"
    "• از `;` در پایان هر query استفاده کنید\n"
    "• فاصله‌ها و enter های اضافی مشکلی ندارند\n"
    "• هر شماره دانشجویی حداکثر ۱۰ بار می‌تواند هر تمرین را ارسال کند\n\n"
    "📝 نمونه فرمت صحیح:\n"
    "```sql\n"
    "# number 1\n"
    "SELECT id, name, grade\n"
    "FROM students\n"
    "WHERE grade >= 15;\n\n"
    "# number 2\n"
    "SELECT COUNT(*) as student_count\n"
    "FROM students\n"
    "WHERE grade >= 15;\n"
    "```\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
)

# ==================== ابزارهای کمکی ====================

def get_persian_datetime():
    tehran_tz = pytz.timezone('Asia/Tehran')
    now = datetime.now(tehran_tz)
    persian_date = jdatetime.datetime.fromgregorian(datetime=now)

    persian_weekdays = {
        0: 'شنبه', 1: 'یکشنبه', 2: 'دوشنبه', 3: 'سه‌شنبه',
        4: 'چهارشنبه', 5: 'پنج‌شنبه', 6: 'جمعه'
    }
    persian_months = {
        1: 'فروردین', 2: 'اردیبهشت', 3: 'خرداد', 4: 'تیر',
        5: 'مرداد', 6: 'شهریور', 7: 'مهر', 8: 'آبان',
        9: 'آذر', 10: 'دی', 11: 'بهمن', 12: 'اسفند'
    }

    weekday_name = persian_weekdays[persian_date.weekday()]
    month_name = persian_months[persian_date.month]

    formatted_date = f"{weekday_name} {persian_date.day} {month_name} {persian_date.year}"
    formatted_time = f"{persian_date.hour:02d}:{persian_date.minute:02d}:{persian_date.second:02d}"

    return formatted_date, formatted_time

def get_student_info(student_id: str, password: str = None):
    try:
        with engine.begin() as conn:
            if password is None:
                result = conn.execute(
                    text("SELECT name, major, pass FROM stuid WHERE student_id = :student_id"),
                    {"student_id": student_id}
                ).fetchone()
                if result:
                    return result[0], result[1], result[2]
                return None, None, None
            else:
                result = conn.execute(
                    text("SELECT name, major FROM stuid WHERE student_id = :student_id AND pass = :password"),
                    {"student_id": student_id, "password": password}
                ).fetchone()
                if result:
                    return result[0], result[1], None
                return None, None, None
    except Exception as e:
        print(f"Error getting student info: {e}")
        return None, None, None

def update_password(student_id: str, new_password: str):
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE stuid SET pass = :new_password WHERE student_id = :student_id"),
                {"new_password": new_password, "student_id": student_id}
            )
            return True
    except Exception as e:
        print(f"Error updating password: {e}")
        return False

def update_email(student_id: str, new_email: str):
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE stuid SET email = :new_email WHERE student_id = :student_id"),
                {"new_email": new_email, "student_id": student_id}
            )
            return True
    except Exception as e:
        print(f"Error updating email: {e}")
        return False

def get_student_email(student_id: str):
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("SELECT email FROM stuid WHERE student_id = :student_id"),
                {"student_id": student_id}
            ).fetchone()
            return result[0] if result and result[0] else None
    except Exception as e:
        print(f"Error getting student email: {e}")
        return None

def get_submission_count(student_id: str, hw: str) -> int:
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM student_results WHERE student_id = :student_id AND hw = :hw"),
                {"student_id": student_id, "hw": hw}
            ).fetchone()
            return result[0] if result else 0
    except Exception as e:
        print(f"Error getting submission count: {e}")
        return 0

def get_main_menu():
    return ReplyKeyboardMarkup([
        ["🚀 تمرین جدید"],
        ["🧪 اجرای SQL سرکلاس"],
        ["🔐 تغییر رمز عبور", "📧 ثبت ایمیل اطلاع‌رسانی"],
        ["🔚 پایان"]
    ], one_time_keyboard=True, resize_keyboard=True)

def get_hw_selection_menu():
    hw_with_back = [
        ["📝 تمرین 3", "📝 تمرین 4"],
        ["📝 تمرین 5", "📝 تمرین 6"],
        ["🔙 بازگشت به منو اصلی"]
    ]
    return ReplyKeyboardMarkup(hw_with_back, one_time_keyboard=True, resize_keyboard=True)

# ==================== شروع ====================

def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    update.message.reply_text(welcome_text, parse_mode='Markdown')
    user_state[chat_id] = "waiting_student_id"
    update.message.reply_text(
        "🆔 لطفاً شماره دانشجویی خود را وارد کنید:", 
        reply_markup=ReplyKeyboardRemove()
    )

# ==================== هندل پیام‌ها ====================

def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text
    
    if text == "🔙 بازگشت به منو اصلی":
        user_state[chat_id] = "completed"
        update.message.reply_text("🏠 بازگشت به منو اصلی:", reply_markup=get_main_menu())
        return
    
    # --- لاگین ---
    if user_state.get(chat_id) == "waiting_student_id":
        student_id = text.strip()
        name, major, _ = get_student_info(student_id)
        
        if name and major:
            context.user_data["student_id"] = student_id
            context.user_data["name"] = name
            context.user_data["major"] = major
            user_state[chat_id] = "waiting_password"
            update.message.reply_text("🔐 لطفاً رمز عبور خود را وارد کنید:")
        else:
            update.message.reply_text("❌ شماره دانشجویی یافت نشد.\n🔍 لطفاً شماره دانشجویی صحیح وارد کنید:")
    
    elif user_state.get(chat_id) == "waiting_password":
        password = text.strip()
        student_id = context.user_data["student_id"]
        name, major, _ = get_student_info(student_id, password)
        
        if name and major:
            user_state[chat_id] = "completed"
            reply_markup = get_main_menu()
            update.message.reply_text(
                f"🎉 ورود موفقیت‌آمیز!\n👤 {name}\n📚 رشته: {major}\n\n✨ خوش آمدید!\n\n🔽 یکی از گزینه‌ها را انتخاب کنید:",
                reply_markup=reply_markup
            )
        else:
            update.message.reply_text("❌ رمز عبور اشتباه است.\n🔐 لطفاً رمز عبور صحیح وارد کنید:")
    
    # --- انتخاب تمرین ---
    elif user_state.get(chat_id) == "waiting_hw":
        if "تمرین 3" in text: hw_number = "3"
        elif "تمرین 4" in text: hw_number = "4"
        elif "تمرین 5" in text: hw_number = "5"
        elif "تمرین 6" in text: hw_number = "6"
        else: hw_number = None

        if hw_number:
            student_id = context.user_data["student_id"]
            submission_count = get_submission_count(student_id, hw_number)
            
            if submission_count >= 10:
                update.message.reply_text(
                    f"🚫 شما قبلاً ۱۰ بار تمرین {hw_number} را ارسال کرده‌اید.",
                    reply_markup=get_hw_selection_menu()
                )
                return
            
            context.user_data["hw"] = hw_number
            user_state[chat_id] = "waiting_sql"
            remaining_attempts = 10 - submission_count
            update.message.reply_text(
                f"✅ تمرین {hw_number} انتخاب شد!\n📊 باقی‌مانده: {remaining_attempts}\n💻 SQL خود را ارسال کنید:",
                reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True, resize_keyboard=True)
            )
        else:
            update.message.reply_text("❌ شماره تمرین معتبر نیست.")
    
    # --- اجرای SQL تمرین‌ها ---
    elif user_state.get(chat_id) == "waiting_sql":
        sql_text = text
        process_sql(update, context, sql_text)

    # --- اجرای SQL سرکلاس ---
    elif user_state.get(chat_id) == "waiting_class_sql":
        sql_query = text.strip()
        
        if not sql_query.lower().startswith("select"):
            update.message.reply_text("❌ فقط دستورات SELECT مجاز هستند.")
            return
        if "test" not in sql_query.lower():
            update.message.reply_text("❌ فقط روی جدول test اجازه دارید query اجرا کنید.")
            return
        
        try:
            with engine.begin() as conn:
                rows = conn.execute(text(sql_query)).fetchall()
                if not rows:
                    update.message.reply_text("📭 هیچ نتیجه‌ای پیدا نشد.")
                else:
                    preview = rows[:10]
                    formatted = "\n".join([str(row) for row in preview])
                    update.message.reply_text(f"📊 نتیجه:\n\n{formatted}")
        except Exception as e:
            update.message.reply_text(f"⚠️ خطا در اجرای query:\n{e}")

    # --- منو اصلی ---
    elif user_state.get(chat_id) == "completed":
        if text == "🚀 تمرین جدید":
            user_state[chat_id] = "waiting_hw"
            update.message.reply_text("📝 شماره تمرین را انتخاب کنید:", reply_markup=get_hw_selection_menu())
        
        elif text == "🧪 اجرای SQL سرکلاس":
            user_state[chat_id] = "waiting_class_sql"
            update.message.reply_text(
                "🧪 دستور SELECT خود را وارد کنید (فقط روی جدول test مجاز است):",
                reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True, resize_keyboard=True)
            )

# ==================== فایل SQL ====================

def handle_document(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    if user_state.get(chat_id) != "waiting_sql":
        update.message.reply_text("لطفاً از /start شروع کنید.")
        return
    
    document: Document = update.message.document
    if not document.file_name.endswith(".sql"):
        update.message.reply_text("❌ فقط فایل .sql مجاز است.")
        return
    
    file = document.get_file()
    sql_text = file.download_as_bytearray().decode("utf-8")
    process_sql(update, context, sql_text)

# ==================== پردازش تمرین‌ها ====================

def process_sql(update: Update, context: CallbackContext, sql_text: str):
    chat_id = update.message.chat_id
    
    queries = re.split(r"#\s*number\s*\d+", sql_text, flags=re.IGNORECASE)
    queries = [q.strip() for q in queries if q.strip()]
    
    hw = context.user_data["hw"]
    name = context.user_data["name"]
    student_id = context.user_data["student_id"]
    major = context.user_data["major"]
    
    submission_count = get_submission_count(student_id, hw)
    if submission_count >= 10:
        update.message.reply_text(f"❌ بیش از ۱۰ بار تمرین {hw} ارسال شده است.", reply_markup=get_main_menu())
        user_state[chat_id] = "completed"
        return
    
    correct_count = 0
    incorrect_questions = []
    
    with engine.begin() as conn:
        for i, student_query in enumerate(queries):
            question_number = i + 1
            try:
                student_rows = conn.execute(text(student_query)).fetchall()
                if major == "آمار":
                    reference_table = f"hw{hw}_q{question_number}_stat_reference"
                else:
                    reference_table = f"hw{hw}_q{question_number}_cs_reference"
                
                reference_rows = conn.execute(text(f"SELECT * FROM {reference_table}")).fetchall()
                
                if set(student_rows) == set(reference_rows):
                    correct_count += 1
                else:
                    incorrect_questions.append(question_number)
                    
            except Exception as e:
                print(f"Error executing query {question_number}: {e}")
                incorrect_questions.append(question_number)
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS student_results (
                id SERIAL PRIMARY KEY,
                student_id TEXT NOT NULL,
                name TEXT NOT NULL,
                major TEXT NOT NULL,
                hw TEXT NOT NULL,
                correct_count INTEGER NOT NULL,
                submission_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        conn.execute(
            text("INSERT INTO student_results (student_id, name, major, hw, correct_count) VALUES (:student_id, :name, :major, :hw, :correct_count)"),
            {"student_id": student_id, "name": name, "major": major, "hw": hw, "correct_count": correct_count}
        )
    
    persian_date, persian_time = get_persian_datetime()
    result_message = f"🎉 نتیجه تصحیح!\n📅 {persian_date} 🕐 {persian_time}\n👤 {name} ({student_id})\n📚 {major}\n📝 تمرین {hw}\n📊 {correct_count}/{len(queries)} صحیح\n"
    if incorrect_questions:
        result_message += "❌ سوال‌های غلط: " + ", ".join(map(str, incorrect_questions))
    else:
        result_message += "🏆 همه صحیح!"
    
    update.message.reply_text(result_message, reply_markup=get_main_menu())
    user_state[chat_id] = "completed"

# ==================== راه‌اندازی ====================

updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
dp.add_handler(MessageHandler(Filters.document, handle_document))
updater.start_polling()

# ==================== وب سرور ====================

app = Flask('')
@app.route('/')
def home():
    return "ربات تلگرام فعال است ✅"

def run():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

Thread(target=run).start()
updater.idle()
