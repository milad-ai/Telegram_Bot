
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
from tabulate import tabulate

# ==================== تنظیمات ====================
TOKEN = os.environ.get("BOT_TOKEN")
DB_URI = os.environ.get("DB_URI")
if not TOKEN or not DB_URI:
    raise ValueError("BOT_TOKEN and DB_URI must be set!")

engine = create_engine(DB_URI, pool_pre_ping=True)
user_state = {}

# ==================== منوها ====================
def get_main_menu():
    return ReplyKeyboardMarkup([
        ["🚀 تمرین جدید"],
        ["🧪 اجرای SQL سرکلاس"],
        ["🔐 تغییر رمز عبور", "📧 ثبت ایمیل اطلاع‌رسانی"],
        ["🔚 پایان"]
    ], one_time_keyboard=True, resize_keyboard=True)

def get_hw_selection_menu():
    return ReplyKeyboardMarkup([
        ["📝 تمرین 3", "📝 تمرین 4"],
        ["📝 تمرین 5", "📝 تمرین 6"],
        ["🔙 بازگشت به منو اصلی"]
    ], one_time_keyboard=True, resize_keyboard=True)

# ==================== توابع کمکی ====================
def get_persian_datetime():
    tz = pytz.timezone('Asia/Tehran')
    now = datetime.now(tz)
    pd = jdatetime.datetime.fromgregorian(datetime=now)
    weekdays = ['شنبه','یکشنبه','دوشنبه','سه‌شنبه','چهارشنبه','پنج‌شنبه','جمعه']
    months = ['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند']
    return f"{weekdays[pd.weekday()]} {pd.day} {months[pd.month-1]} {pd.year}", f"{pd.hour:02d}:{pd.minute:02d}:{pd.second:02d}"

def get_student_info(student_id: str, password: str = None):
    try:
        with engine.begin() as conn:
            if password is None:
                result = conn.execute(
                    text("SELECT name, major, pass FROM stuid WHERE student_id = :student_id"),
                    {"student_id": student_id}
                ).fetchone()
                if result: return result[0], result[1], result[2]
            else:
                result = conn.execute(
                    text("SELECT name, major FROM stuid WHERE student_id = :student_id AND pass = :password"),
                    {"student_id": student_id, "password": password}
                ).fetchone()
                if result: return result[0], result[1], None
    except Exception as e:
        print("Error get_student_info:", e)
    return None, None, None

def update_password(student_id: str, new_password: str):
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE stuid SET pass=:new_password WHERE student_id=:student_id"),
                {"new_password": new_password, "student_id": student_id}
            )
            return True
    except Exception as e:
        print("Error update_password:", e)
        return False

def update_email(student_id: str, new_email: str):
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE stuid SET email=:new_email WHERE student_id=:student_id"),
                {"new_email": new_email, "student_id": student_id}
            )
            return True
    except Exception as e:
        print("Error update_email:", e)
        return False

def get_student_email(student_id: str):
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("SELECT email FROM stuid WHERE student_id=:student_id"),
                {"student_id": student_id}
            ).fetchone()
            return result[0] if result else None
    except Exception as e:
        print("Error get_student_email:", e)
        return None

def get_submission_count(student_id: str, hw: str) -> int:
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM student_results WHERE student_id=:student_id AND hw=:hw"),
                {"student_id": student_id, "hw": hw}
            ).fetchone()
            return result[0] if result else 0
    except Exception as e:
        print("Error get_submission_count:", e)
        return 0

# ==================== دستورات /start ====================
def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    update.message.reply_text("🎓 خوش آمدید به ربات پایگاه داده!\n📋 لطفاً شماره دانشجویی خود را وارد کنید:")
    user_state[chat_id] = "waiting_student_id"

# ==================== پیام‌ها ====================
def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text_msg = update.message.text
    state = user_state.get(chat_id)

    if text_msg == "🔙 بازگشت به منو اصلی":
        user_state[chat_id] = "completed"
        update.message.reply_text("🏠 بازگشت به منو اصلی:", reply_markup=get_main_menu())
        return

    # ---------- ورود دانشجو ----------
    if state == "waiting_student_id":
        student_id = text_msg.strip()
        name, major, _ = get_student_info(student_id)
        if name:
            context.user_data["student_id"] = student_id
            context.user_data["name"] = name
            context.user_data["major"] = major
            user_state[chat_id] = "waiting_password"
            update.message.reply_text("🔐 لطفاً رمز عبور خود را وارد کنید:")
        else:
            update.message.reply_text("❌ شماره دانشجویی یافت نشد. دوباره وارد کنید:")

    elif state == "waiting_password":
        password = text_msg.strip()
        student_id = context.user_data["student_id"]
        name, major, _ = get_student_info(student_id, password)
        if name:
            user_state[chat_id] = "completed"
            update.message.reply_text(f"🎉 ورود موفقیت‌آمیز!\n👤 {name}\n📚 رشته: {major}", reply_markup=get_main_menu())
        else:
            update.message.reply_text("❌ رمز اشتباه است. دوباره وارد کنید:")

    # ---------- ثبت ایمیل ----------
    elif state == "waiting_new_email":
        new_email = text_msg.strip()
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', new_email):
            update.message.reply_text("❌ فرمت ایمیل صحیح نیست. دوباره وارد کنید:")
            return
        student_id = context.user_data["student_id"]
        if update_email(student_id, new_email):
            user_state[chat_id] = "completed"
            update.message.reply_text(f"✅ ایمیل ثبت شد: {new_email}", reply_markup=get_main_menu())
        else:
            update.message.reply_text("❌ خطا در ثبت ایمیل!", reply_markup=get_main_menu())

    # ---------- تغییر پسورد ----------
    elif state == "waiting_new_password":
        new_password = text_msg.strip()
        if len(new_password) < 4:
            update.message.reply_text("❌ رمز باید حداقل 4 کاراکتر باشد. دوباره وارد کنید:")
            return
        student_id = context.user_data["student_id"]
        if update_password(student_id, new_password):
            user_state[chat_id] = "completed"
            update.message.reply_text("✅ رمز عبور تغییر یافت.", reply_markup=get_main_menu())
        else:
            update.message.reply_text("❌ خطا در تغییر رمز!", reply_markup=get_main_menu())

    # ---------- منو اصلی ----------
    elif state == "completed":
        if text_msg == "🚀 تمرین جدید":
            user_state[chat_id] = "waiting_hw"
            update.message.reply_text("📝 شماره تمرین را انتخاب کنید:", reply_markup=get_hw_selection_menu())
        elif text_msg == "🧪 اجرای SQL سرکلاس":
            user_state[chat_id] = "running_test_sql"
            update.message.reply_text("💻 لطفاً دستور SELECT خود را وارد کنید (روی جدول‌هایی که نامشان شامل `test` است):")
        elif text_msg == "🔐 تغییر رمز عبور":
            user_state[chat_id] = "waiting_new_password"
            update.message.reply_text("🔐 رمز عبور جدید خود را وارد کنید:")
        elif text_msg == "📧 ثبت ایمیل اطلاع‌رسانی":
            student_id = context.user_data["student_id"]
            current_email = get_student_email(student_id)
            status = f"📧 ایمیل فعلی: {current_email}" if current_email else "📧 ایمیل ثبت نشده"
            user_state[chat_id] = "waiting_new_email"
            update.message.reply_text(f"📧 ثبت/ویرایش ایمیل\n{status}\nلطفاً ایمیل جدید را وارد کنید:")
        elif text_msg == "🔚 پایان":
            update.message.reply_text("🙏 متشکرم از استفاده! برای شروع دوباره /start را بزنید.", reply_markup=get_main_menu())

    # ---------- انتخاب تمرین ----------
    elif state == "waiting_hw":
        hw_number = None
        if "تمرین 3" in text_msg: hw_number = "3"
        elif "تمرین 4" in text_msg: hw_number = "4"
        elif "تمرین 5" in text_msg: hw_number = "5"
        elif "تمرین 6" in text_msg: hw_number = "6"

        if hw_number:
            student_id = context.user_data["student_id"]
            submission_count = get_submission_count(student_id, hw_number)
            if submission_count >= 10:
                update.message.reply_text(f"🚫 شما قبلاً ۱۰ بار تمرین {hw_number} را ارسال کرده‌اید.", reply_markup=get_hw_selection_menu())
                return
            context.user_data["hw"] = hw_number
            user_state[chat_id] = "waiting_sql"
            remaining = 10 - submission_count
            update.message.reply_text(f"✅ تمرین {hw_number} انتخاب شد!\nتعداد ارسال باقی مانده: {remaining}\n💻 SQL خود را ارسال کنید:")
        else:
            update.message.reply_text("❌ لطفاً شماره تمرین معتبر انتخاب کنید.")

    # ---------- SQL تمرین ----------
    elif state == "waiting_sql":
        process_hw_sql(update, context, text_msg)

    # ---------- SQL سرکلاس ----------
    elif state == "running_test_sql":
        process_test_sql(update, context, text_msg)

# ==================== پردازش SQL تمرین ====================
def process_hw_sql(update, context, sql_text):
    chat_id = update.message.chat_id
    hw = context.user_data.get("hw")
    student_id = context.user_data.get("student_id")
    name = context.user_data.get("name")
    major = context.user_data.get("major")

    queries = re.split(r"#\s*number\s*\d+", sql_text, flags=re.IGNORECASE)
    queries = [q.strip() for q in queries if q.strip()]

    correct_count = 0
    incorrect_questions = []

    with engine.begin() as conn:
        for i, student_query in enumerate(queries):
            qnum = i + 1
            try:
                student_rows = conn.execute(text(student_query)).fetchall()
                ref_table = f"hw{hw}_q{qnum}_{'stat' if major=='آمار' else 'cs'}_reference"
                ref_rows = conn.execute(text(f"SELECT * FROM {ref_table}")).fetchall()
                if set(student_rows) == set(ref_rows):
                    correct_count += 1
                else:
                    incorrect_questions.append(qnum)
            except Exception as e:
                incorrect_questions.append(qnum)

        # ثبت نتایج
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
        conn.execute(text("""
            INSERT INTO student_results (student_id,name,major,hw,correct_count)
            VALUES (:student_id,:name,:major,:hw,:correct_count)
        """), {"student_id": student_id, "name": name, "major": major, "hw": hw, "correct_count": correct_count})

    pd, pt = get_persian_datetime()
    result_message = f"🎉 تمرین تصحیح شد!\n📅 {pd}\n🕐 {pt}\n👤 {name}\n📝 تمرین: {hw}\n✅ صحیح: {correct_count}/{len(queries)}"
    if incorrect_questions:
        result_message += f"\n❌ نادرست: {', '.join(map(str, incorrect_questions))}"
    update.message.reply_text(result_message, reply_markup=get_main_menu())
    user_state[chat_id] = "completed"

# ==================== پردازش SQL سرکلاس ====================
def process_test_sql(update, context, sql_text):
    chat_id = update.message.chat_id
    try:
        sql_lower = sql_text.lower()
        if "select" not in sql_lower:
            update.message.reply_text("❌ فقط دستورات SELECT مجاز هستند.")
            return
        # فقط جدول‌هایی که نامشان شامل test است
        tables = [t[0] for t in engine.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).fetchall()]
        if not any("test" in t.lower() for t in tables):
            update.message.reply_text("❌ هیچ جدول test موجود نیست.")
            return
        # اجرای دستور
        with engine.begin() as conn:
            rows = conn.execute(text(sql_text)).fetchall()
            if not rows:
                update.message.reply_text("✅ نتیجه: هیچ سطری یافت نشد.")
            else:
                columns = rows[0].keys()
                table_str = tabulate(rows, headers=columns, tablefmt="grid")
                update.message.reply_text(f"📊 خروجی:\n{table_str}")
    except Exception as e:
        update.message.reply_text(f"⚠️ خطا در اجرای query: {str(e)}")
    user_state[chat_id] = "completed"

# ==================== راه‌اندازی ربات ====================
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
updater.start_polling()

# ==================== وب سرور Flask برای Keep Alive ====================
app = Flask('')
@app.route('/')
def home(): return "ربات تلگرام فعال است ✅"
def run(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
Thread(target=run).start()
updater.idle()
