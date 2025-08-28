import os
import re
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, Document, ParseMode
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

# ==================== دستورات /start ====================
def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    update.message.reply_text(
        "🎓 خوش آمدید به ربات پایگاه داده!\n\n📋 برای شروع /start را بزنید."
    )
    user_state[chat_id] = "waiting_student_id"
    update.message.reply_text("🆔 شماره دانشجویی خود را وارد کنید:", reply_markup=ReplyKeyboardRemove())

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
            update.message.reply_text(
                f"🎉 ورود موفقیت‌آمیز!\n👤 {name}\n📚 رشته: {major}",
                reply_markup=get_main_menu()
            )
        else:
            update.message.reply_text("❌ رمز اشتباه است. دوباره وارد کنید:")

    # ---------- منو اصلی ----------
    elif state == "completed":
        if text_msg == "🚀 تمرین جدید":
            user_state[chat_id] = "waiting_hw"
            update.message.reply_text("📝 شماره تمرین را انتخاب کنید:", reply_markup=get_hw_selection_menu())
        elif text_msg == "🧪 اجرای SQL سرکلاس":
            user_state[chat_id] = "running_test_sql"
            update.message.reply_text(
                "💻 SQL خود را برای جدول `test` ارسال کنید:\n⚠️ فقط SELECT مجاز است",
                reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], resize_keyboard=True)
            )
        elif text_msg == "🔐 تغییر رمز عبور":
            user_state[chat_id] = "waiting_new_password"
            update.message.reply_text("🔐 رمز عبور جدید خود را وارد کنید:")
        elif text_msg == "📧 ثبت ایمیل اطلاع‌رسانی":
            student_id = context.user_data["student_id"]
            email = get_student_email(student_id)
            user_state[chat_id] = "waiting_new_email"
            update.message.reply_text(f"📧 ایمیل فعلی: {email or 'ثبت نشده'}\nایمیل جدید را وارد کنید:")
        elif text_msg == "🔚 پایان":
            update.message.reply_text("🙏 متشکرم!\n/start برای شروع دوباره", reply_markup=get_main_menu())

    # ---------- اجرای SQL سرکلاس ----------
    elif state == "running_test_sql":
        sql_query = text_msg.strip()

        if not sql_query.lower().startswith("select"):
            update.message.reply_text("❌ فقط SELECT مجاز است.")
            return

        # فقط جدول test مجاز است
        forbidden = ["stuid", "student_results", "hw"]
        if "test" not in sql_query.lower() or any(t in sql_query.lower() for t in forbidden):
            update.message.reply_text("❌ اجازه دسترسی به این جدول وجود ندارد. فقط جدول `test` مجاز است.")
            return

        try:
            with engine.begin() as conn:
                rows = conn.execute(text(sql_query)).fetchall()
                if not rows:
                    update.message.reply_text("📭 هیچ نتیجه‌ای پیدا نشد.")
                else:
                    headers = rows[0].keys() if hasattr(rows[0], "_mapping") else range(len(rows[0]))
                    table = tabulate([tuple(r) for r in rows], headers=headers, tablefmt="github")
                    update.message.reply_text(f"📊 نتیجه:\n\n```\n{table}\n```", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            update.message.reply_text(f"⚠️ خطا در اجرای query: {e}")

# ==================== اجرای ربات ====================
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
updater.start_polling()

# ==================== وب سرور Flask ====================
app = Flask('')
@app.route('/')
def home(): return "ربات تلگرام فعال است ✅"
def run(): app.run(host="0.0.
