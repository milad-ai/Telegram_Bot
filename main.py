
import os
import re
import json
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
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # شناسه کاربری ادمین

if not TOKEN or not DB_URI or not ADMIN_CHAT_ID:
    raise ValueError("BOT_TOKEN, DB_URI and ADMIN_CHAT_ID must be set!")

engine = create_engine(DB_URI, pool_pre_ping=True)
user_state = {}

welcome_text = (
    "🎓 خوش آمدید به ربات پایگاه داده! 🎓\n\n"
    "✨ این ربات برای درس پایگاه داده دانشجویان در نیم‌سال اول ۱۴۰۵-۱۴۰۴\n"
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

def get_allowed_tables():
    """لیست جدول‌های مجاز را از دیتابیس دریافت می‌کند"""
    try:
        with engine.begin() as conn:
            result = conn.execute(text("SELECT table_name FROM allowed_tables"))
            return [row[0] for row in result.fetchall()]
    except Exception as e:
        print(f"Error getting allowed tables: {e}")
        return ['test']  # جدول پیش‌فرض در صورت بروز خطا

def get_persian_datetime():
    """تاریخ و ساعت فعلی را به وقت تهران و به فارسی برمی‌گرداند"""
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

def send_notification_to_admin(context: CallbackContext, message: str):
    """ارسال پیام اطلاع‌رسانی به ادمین"""
    try:
        context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=message)
    except Exception as e:
        print(f"Error sending notification to admin: {e}")

def get_student_info(student_id: str, password: str = None):
    """اطلاعات دانشجو را از جدول stuid دریافت می‌کند"""
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
    """رمز عبور دانشجو را به‌روزرسانی می‌کند"""
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
    """ایمیل دانشجو را به‌روزرسانی می‌کند و تاریخ تغییر را ثبت می‌کند"""
    try:
        with engine.begin() as conn:
            try:
                conn.execute(text("ALTER TABLE stuid ADD COLUMN IF NOT EXISTS email_history TEXT"))
            except Exception as alter_error:
                print(f"Note: email_history column may already exist: {alter_error}")
                pass
            
            result = conn.execute(
                text("SELECT email, email_history FROM stuid WHERE student_id = :student_id"),
                {"student_id": student_id}
            ).fetchone()
            
            old_email = result[0] if result and result[0] else None
            email_history = result[1] if result and result[1] else ""
            
            persian_date, persian_time = get_persian_datetime()
            history_entry = f"{persian_date} {persian_time}: {old_email or 'None'} -> {new_email}\n"
            new_history = (history_entry + email_history)[:1000]
            
            conn.execute(
                text("UPDATE stuid SET email = :new_email, email_history = :new_history WHERE student_id = :student_id"),
                {"new_email": new_email, "new_history": new_history, "student_id": student_id}
            )
            return True
    except Exception as e:
        print(f"Error updating email: {e}")
        return False

def get_student_email(student_id: str):
    """ایمیل فعلی دانشجو را دریافت می‌کند"""
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
    """تعداد ارسال‌های قبلی دانشجو برای یک تمرین خاص را برمی‌گرداند"""
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

def save_teacher_query(student_id: str, student_name: str, major: str, query: str, output: str) -> bool:
    """ذخیره کوئری و خروجی آن در جدول teacher_queries"""
    try:
        with engine.begin() as conn:
            # ایجاد جدول اگر وجود ندارد
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS teacher_queries (
                    id SERIAL PRIMARY KEY,
                    student_id TEXT NOT NULL,
                    student_name TEXT NOT NULL,
                    major TEXT NOT NULL,
                    query TEXT NOT NULL,
                    output TEXT,
                    submission_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # درج داده
            conn.execute(
                text("""
                    INSERT INTO teacher_queries 
                    (student_id, student_name, major, query, output)
                    VALUES (:student_id, :student_name, :major, :query, :output)
                """),
                {
                    "student_id": student_id,
                    "student_name": student_name,
                    "major": major,
                    "query": query,
                    "output": output
                }
            )
            return True
    except Exception as e:
        print(f"Error saving teacher query: {e}")
        return False

def get_main_menu():
    return ReplyKeyboardMarkup([
        ["🚀 تمرین جدید"],
        ["🔐 تغییر رمز عبور", "📧 ثبت ایمیل اطلاع‌رسانی"],
        ["📊 اجرای کدهای تمرین‌های سرکلاسی"],
        ["🔚 پایان"]
    ], one_time_keyboard=True, resize_keyboard=True)

def get_hw_selection_menu():
    hw_with_back = [
        ["📝 تمرین 3", "📝 تمرین 4"],
        ["📝 تمرین 5", "📝 تمرین 6"],
        ["🔙 بازگشت به منو اصلی"]
    ]
    return ReplyKeyboardMarkup(hw_with_back, one_time_keyboard=True, resize_keyboard=True)

def is_query_allowed(query: str) -> bool:
    """بررسی می‌کند که آیا کوئری فقط روی جدول‌های مجاز اجرا می‌شود یا خیر"""
    query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
    query = re.sub(r'/\*.*?\*/', '', query, flags=re.DOTALL)
    
    query_lower = query.lower().strip()
    
    if not query_lower.startswith('select'):
        return False
    
    forbidden_keywords = ['insert', 'update', 'delete', 'drop', 'create', 'alter', 'truncate']
    for keyword in forbidden_keywords:
        if f' {keyword} ' in f' {query_lower} ':
            return False
    
    # دریافت لیست جدول‌های مجاز
    allowed_tables = get_allowed_tables()
    
    # استخراج نام جدول‌های استفاده شده در کوئری
    from_tables = re.findall(r'\bfrom\s+(\w+)', query_lower, flags=re.IGNORECASE)
    join_tables = re.findall(r'\bjoin\s+(\w+)', query_lower, flags=re.IGNORECASE)
    
    all_tables = from_tables + join_tables
    
    # بررسی اینکه همه جدول‌های استفاده شده در لیست مجازها هستند
    if all_tables and not all(table in allowed_tables for table in all_tables):
        return False
    
    return True

# ==================== توابع اصلی ====================

def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    update.message.reply_text(welcome_text, parse_mode='Markdown')
    user_state[chat_id] = "waiting_student_id"
    update.message.reply_text(
        "🆔 لطفاً شماره دانشجویی خود را وارد کنید:", 
        reply_markup=ReplyKeyboardRemove()
    )

def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text
    
    if text == "🔙 بازگشت به منو اصلی":
        user_state[chat_id] = "completed"
        update.message.reply_text("🏠 بازگشت به منو اصلی:", reply_markup=get_main_menu())
        return
    
    if user_state.get(chat_id) == "waiting_student_id":
        student_id = text.strip()
        name, major, _ = get_student_info(student_id)
        
        if name and major:
            context.user_data["student_id"] = student_id
            context.user_data["name"] = name
            context.user_data["major"] = major
            user_state[chat_id] = "waiting_password"
            update.message.reply_text(
                "🔐 لطفاً رمز عبور خود را وارد کنید:"
            )
        else:
            update.message.reply_text(
                "❌ شماره دانشجویی یافت نشد.\n"
                "🔍 لطفاً شماره دانشجویی صحیح وارد کنید:"
            )
    
    elif user_state.get(chat_id) == "waiting_password":
        password = text.strip()
        student_id = context.user_data["student_id"]
        name, major, _ = get_student_info(student_id, password)
        
        if name and major:
            user_state[chat_id] = "completed"
            reply_markup = get_main_menu()
            update.message.reply_text(
                f"🎉 ورود موفقیت‌آمیز!\n"
                f"👤 دانشجوی عزیز {name}\n"
                f"📚 رشته: {major}\n\n"
                "✨ به ربات پایگاه داده خوش آمدید!\n\n"
                "🔽 لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=reply_markup
            )
        else:
            update.message.reply_text(
                "❌ رمز عبور اشتباه است.\n"
                "🔐 لطفاً رمز عبور صحیح وارد کنید:"
            )
    
    elif user_state.get(chat_id) == "waiting_hw":
        if text == "🔙 بازگشت به منو اصلی":
            user_state[chat_id] = "completed"
            update.message.reply_text("🏠 بازگشت به منو اصلی:", reply_markup=get_main_menu())
            return
            
        hw_number = None
        if "تمرین 3" in text:
            hw_number = "3"
        elif "تمرین 4" in text:
            hw_number = "4"
        elif "تمرین 5" in text:
            hw_number = "5"
        elif "تمرین 6" in text:
            hw_number = "6"
            
        if hw_number:
            student_id = context.user_data["student_id"]
            hw = hw_number
            
            submission_count = get_submission_count(student_id, hw)
            
            if submission_count >= 10:
                update.message.reply_text(
                    f"🚫 شما قبلاً ۱۰ بار تمرین {hw} را ارسال کرده‌اید و حق ارسال مجدد ندارید.\n\n"
                    "📝 لطفاً تمرین دیگری انتخاب کنید:",
                    reply_markup=get_hw_selection_menu()
                )
                return
            
            context.user_data["hw"] = hw
            user_state[chat_id] = "waiting_sql"
            remaining_attempts = 10 - submission_count
            update.message.reply_text(
                f"✅ تمرین {hw} انتخاب شد!\n\n"
                f"📊 تعداد ارسال‌های باقی‌مانده: {remaining_attempts}\n\n"
                "💻 حالا SQL خود را ارسال کنید:\n"
                "📄 متن مستقیم یا فایل .sql",
                reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True, resize_keyboard=True)
            )
        else:
            update.message.reply_text("❌ لطفاً شماره تمرین معتبر انتخاب کنید.")
    
    elif user_state.get(chat_id) == "waiting_sql":
        if text == "🔙 بازگشت به منو اصلی":
            user_state[chat_id] = "completed"
            update.message.reply_text("🏠 بازگشت به منو اصلی:", reply_markup=get_main_menu())
            return
            
        sql_text = text
        process_sql(update, context, sql_text)
    
    elif user_state.get(chat_id) == "waiting_classroom_sql":
        if text == "🔙 بازگشت به منو اصلی":
            user_state[chat_id] = "completed"
            update.message.reply_text("🏠 بازگشت به منو اصلی:", reply_markup=get_main_menu())
            return
            
        sql_text = text
        process_classroom_sql(update, context, sql_text)
    
    elif user_state.get(chat_id) == "waiting_teacher_submission_decision":
        if text == "🔙 بازگشت به منو اصلی":
            user_state[chat_id] = "completed"
            update.message.reply_text("🏠 بازگشت به منو اصلی:", reply_markup=get_main_menu())
            return
        
        if text == "✅ بله، ارسال به مدرس":
            # ذخیره کوئری در جدول teacher_queries
            student_id = context.user_data["student_id"]
            name = context.user_data["name"]
            major = context.user_data["major"]
            query = context.user_data.get("last_query", "")
            output = context.user_data.get("last_output", "")
            
            if save_teacher_query(student_id, name, major, query, output):
                # ارسال پیام اطلاع‌رسانی به ادمین
                persian_date, persian_time = get_persian_datetime()
                admin_message = (
                    "📤 کوئری جدید برای بررسی\n\n"
                    f"👤 دانشجو: {name}\n"
                    f"🆔 شماره دانشجویی: {student_id}\n"
                    f"📚 رشته: {major}\n"
                    f"📅 تاریخ: {persian_date}\n"
                    f"🕐 ساعت: {persian_time}\n\n"
                    f"💻 کوئری:\n```sql\n{query[:500]}\n```\n\n"
                    f"📊 تعداد ردیف‌های بازگشتی: {len(json.loads(output)['rows']) if output else 0}"
                )
                send_notification_to_admin(context, admin_message)
                
                update.message.reply_text(
                    "✅ کوئری شما با موفقیت برای بررسی به مدرس ارسال شد!\n\n"
                    "📝 مدرس در اسرع وقت آن را بررسی خواهد کرد.\n\n"
                    "🏠 بازگشت به منو اصلی:",
                    reply_markup=get_main_menu()
                )
            else:
                update.message.reply_text(
                    "❌ خطا در ارسال کوئری به مدرس!\n"
                    "🔄 لطفاً دوباره تلاش کنید.\n\n"
                    "🏠 بازگشت به منو اصلی:",
                    reply_markup=get_main_menu()
                )
            
            user_state[chat_id] = "completed"
        
        elif text == "❌ خیر، فقط نمایش":
            update.message.reply_text(
                "✅ کوئری فقط برای نمایش اجرا شد و ارسال نشد.\n\n"
                "💻 می‌توانید کوئری دیگری اجرا کنید:",
                reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True, resize_keyboard=True)
            )
            user_state[chat_id] = "waiting_classroom_sql"
        
        else:
            update.message.reply_text(
                "❓ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=ReplyKeyboardMarkup([
                    ["✅ بله، ارسال به مدرس"],
                    ["❌ خیر، فقط نمایش"],
                    ["🔙 بازگشت به منو اصلی"]
                ], one_time_keyboard=True, resize_keyboard=True)
            )
    
    elif user_state.get(chat_id) == "completed":
        if text == "🚀 تمرین جدید":
            user_state[chat_id] = "waiting_hw"
            reply_markup = get_hw_selection_menu()
            update.message.reply_text("📝 شماره تمرین جدید را انتخاب کنید:", reply_markup=reply_markup)
        elif text == "🔐 تغییر رمز عبور":
            user_state[chat_id] = "waiting_new_password"
            update.message.reply_text(
                "🔐 رمز عبور جدید خود را وارد کنید:\n\n"
                "⚠️ نکات مهم:\n"
                "• رمز عبور باید حداقل 4 کاراکتر باشد\n",
                reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True, resize_keyboard=True)
            )
        elif text == "📧 ثبت ایمیل اطلاع‌رسانی":
            student_id = context.user_data["student_id"]
            current_email = get_student_email(student_id)
            user_state[chat_id] = "waiting_new_email"
            
            email_status = f"📧 ایمیل فعلی: {current_email}" if current_email else "📧 ایمیل فعلی: ثبت نشده"
            
            update.message.reply_text(
                f"📧 ثبت/ویرایش ایمیل اطلاع‌رسانی\n\n"
                f"{email_status}\n\n"
                "✉️ ایمیل جدید خود را وارد کنید:\n\n"
                "⚠️ نکات مهم:\n"
                "• این ایمیل برای اطلاع‌رسانی‌های مهم استفاده می‌شود\n"
                "• می‌توانید هر زمان آن را تغییر دهید",
                reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True, resize_keyboard=True)
            )
        elif text == "📊 اجرای کدهای تمرین‌های سرکلاسی":
            user_state[chat_id] = "waiting_classroom_sql"
            
            # دریافت لیست جدول‌های مجاز برای نمایش به کاربر
            allowed_tables = get_allowed_tables()
            tables_list = "\n".join([f"• {table}" for table in allowed_tables])
            
            update.message.reply_text(
                f"📊 حالت اجرای کدهای تمرین‌های سرکلاسی\n\n"
                f"✅ جدول‌های مجاز:\n{tables_list}\n\n"
                "⚠️ محدودیت‌های این بخش:\n"
                "• فقط دستورات SELECT مجاز هستند\n"
                "• فقط می‌توانید از جدول‌های بالا استفاده کنید\n"
                "• دستورات INSERT, UPDATE, DELETE, DROP, CREATE, ALTER ممنوع هستند\n"
                "• سایر جدول‌ها غیرقابل دسترسی هستند\n\n"
                "💻 لطفاً کوئری SELECT خود را ارسال کنید:",
                reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True, resize_keyboard=True)
            )
        elif text == "🔚 پایان":
            update.message.reply_text(
                "🙏 متشکرم از استفاده!\n\n"
                "✨ برای شروع دوباره /start را بزنید.",
                reply_markup=get_main_menu()
            )
        else:
            update.message.reply_text(
                "❓ لطفاً یکی از گزینه‌های منو را انتخاب کنید:",
                reply_markup=get_main_menu()
            )
    
    elif user_state.get(chat_id) == "waiting_new_password":
        if text == "🔙 بازگشت به منو اصلی":
            user_state[chat_id] = "completed"
            update.message.reply_text("🏠 بازگشت به منو اصلی:", reply_markup=get_main_menu())
            return
        
        new_password = text.strip()
        if len(new_password) < 4:
            update.message.reply_text(
                "❌ رمز عبور باید حداقل 4 کاراکتر باشد.\n"
                "🔐 لطفاً رمز عبور جدید را وارد کنید:"
            )
            return
        
        student_id = context.user_data["student_id"]
        if update_password(student_id, new_password):
            user_state[chat_id] = "completed"
            update.message.reply_text(
                "✅ رمز عبور با موفقیت تغییر یافت!\n\n"
                "🔐 رمز عبور جدید شما ثبت شد.\n"
                "💡 لطفاً آن را در جای امنی نگهداری کنید.\n\n"
                "🏠 بازگشت به منو اصلی:",
                reply_markup=get_main_menu()
            )
        else:
            update.message.reply_text(
                "❌ خطا در تغییر رمز عبور!\n"
                "🔄 لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.\n\n"
                "🏠 بازگشت به منو اصلی:",
                reply_markup=get_main_menu()
            )
            user_state[chat_id] = "completed"
    
    elif user_state.get(chat_id) == "waiting_new_email":
        if text == "🔙 بازگشت به منو اصلی":
            user_state[chat_id] = "completed"
            update.message.reply_text("🏠 بازگشت به منو اصلی:", reply_markup=get_main_menu())
            return
        
        new_email = text.strip()
        
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, new_email):
            update.message.reply_text(
                "❌ فرمت ایمیل صحیح نیست.\n\n"
                "💡 مثال صحیح: name@gmail.com\n"
                "📧 لطفاً ایمیل معتبر وارد کنید:"
            )
            return
        
        student_id = context.user_data["student_id"]
        if update_email(student_id, new_email):
            user_state[chat_id] = "completed"
            
            # ارسال پیام اطلاع‌رسانی به ادمین
            persian_date, persian_time = get_persian_datetime()
            admin_message = (
                "🔔 اطلاع‌رسانی ثبت/ویرایش ایمیل\n\n"
                f"👤 دانشجو: {context.user_data['name']}\n"
                f"🆔 شماره دانشجویی: {student_id}\n"
                f"📚 رشته: {context.user_data['major']}\n"
                f"📧 ایمیل جدید: {new_email}\n"
                f"📅 تاریخ: {persian_date}\n"
                f"🕐 ساعت: {persian_time}"
            )
            send_notification_to_admin(context, admin_message)
            
            update.message.reply_text(
                "✅ ایمیل با موفقیت ثبت/به‌روزرسانی شد!\n\n"
                f"📧 ایمیل شما: {new_email}\n\n"
                "📢 از این پس اطلاع‌رسانی‌های مهم به این ایمیل ارسال می‌شود.\n"
                "🔄 می‌توانید هر زمان آن را تغییر دهید.\n\n"
                "🏠 بازگشت به منو اصلی:",
                reply_markup=get_main_menu()
            )
        else:
            update.message.reply_text(
                "❌ خطا در ثبت ایمیل!\n"
                "🔄 لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.\n\n"
                "🏠 بازگشت به منو اصلی:",
                reply_markup=get_main_menu()
            )
            user_state[chat_id] = "completed"

def handle_document(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    
    if user_state.get(chat_id) == "waiting_sql":
        document: Document = update.message.document
        if not document.file_name.endswith(".sql"):
            update.message.reply_text(
                "❌ لطفاً یک فایل معتبر .sql ارسال کنید.\n\n"
                "یا برای بازگشت به منو اصلی دکمه زیر را بزنید:",
                reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True, resize_keyboard=True)
            )
            return
        
        file = document.get_file()
        sql_text = file.download_as_bytearray().decode("utf-8")
        process_sql(update, context, sql_text)
    
    elif user_state.get(chat_id) == "waiting_classroom_sql":
        update.message.reply_text(
            "❌ در حالت اجرای کدهای تمرین‌های سرکلاسی، فقط ارسال متن مستقیم مجاز است.\n"
            "💻 لطفاً کوئری خود را به صورت متن ارسال کنید:",
            reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True, resize_keyboard=True)
        )
    else:
        update.message.reply_text("لطفاً مراحل را از /start دنبال کنید.")

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
        update.message.reply_text(
            f"❌ شما قبلاً ۱۰ بار تمرین {hw} را ارسال کرده‌اید و حق ارسال مجدد ندارید.",
            reply_markup=get_main_menu()
        )
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
        
        try:
            conn.execute(
                text("INSERT INTO student_results (student_id, name, major, hw, correct_count) VALUES (:student_id, :name, :major, :hw, :correct_count)"),
                {"student_id": student_id, "name": name, "major": major, "hw": hw, "correct_count": correct_count}
            )
            print(f"✅ Data inserted successfully for {name} ({student_id}) - Major: {major} - HW{hw}: {correct_count} correct")
        except Exception as e:
            print(f"❌ Error inserting data: {e}")
            update.message.reply_text(f"⚠️ خطا در ذخیره‌سازی: {str(e)}")
            return
    
    persian_date, persian_time = get_persian_datetime()
    
    result_message = f"🎉 تصحیح با موفقیت انجام شد!\n\n"
    result_message += f"┌─────────────────────────────\n"
    result_message += f"│ 📅 تاریخ: {persian_date}\n"
    result_message += f"│ 🕐 ساعت: {persian_time}\n"
    result_message += f"├─────────────────────────────\n"
    result_message += f"│ 👤 دانشجو: {name}\n"
    result_message += f"│ 🆔 شماره دانشجویی: {student_id}\n"
    result_message += f"│ 📚 رشته: {major}\n"
    result_message += f"│ 📝 تمرین: {hw}\n"
    result_message += f"└─────────────────────────────\n\n"
    result_message += f"📊 نتیجه: {correct_count}/{len(queries)} سوال درست است.\n\n"
    
    if major == "آمار":
        email_address = "hw@statdb.ir"
    else:
        email_address = "hw@dbcs.ir"
    
    result_message += f"📧 لطفاً از این پیام اسکرین شات بگیرید و با عنوانی که پیش‌تر توضیح داده شده و تمرین‌های قبلی را ارسال می‌کردید به آدرس:\n"
    result_message += f"✉️ {email_address}\n\n"
    
    if incorrect_questions:
        result_message += "❌ سوال‌های نادرست: " + ", ".join(map(str, incorrect_questions)) + "\n\n"
    else:
        result_message += "🏆 تبریک! تمام سوال‌ها صحیح است!\n\n"
    
    new_submission_count = submission_count + 1
    remaining_attempts = 10 - new_submission_count
    result_message += f"📈 ارسال‌های انجام شده: {new_submission_count}/10\n"
    result_message += f"📊 ارسال‌های باقی‌مانده: {remaining_attempts}\n\n"
    
    if remaining_attempts == 0:
        result_message += "⚠️ این آخرین ارسال شما برای این تمرین بود.\n\n"
    
    result_message += "🤔 آیا می‌خواهید تمرین جدیدی ثبت کنید؟"
    
    update.message.reply_text(result_message, reply_markup=get_main_menu())
    user_state[chat_id] = "completed"

def process_classroom_sql(update: Update, context: CallbackContext, sql_text: str):
    chat_id = update.message.chat_id
    name = context.user_data["name"]
    student_id = context.user_data["student_id"]
    major = context.user_data["major"]
    
    # ذخیره کوئری در context برای استفاده بعدی
    context.user_data["last_query"] = sql_text
    
    if not is_query_allowed(sql_text):
        # دریافت لیست جدول‌های مجاز برای نمایش به کاربر
        allowed_tables = get_allowed_tables()
        tables_list = "\n".join([f"• {table}" for table in allowed_tables])
        
        update.message.reply_text(
            f"❌ کوئری شما مجاز نیست!\n\n"
            f"✅ جدول‌های مجاز:\n{tables_list}\n\n"
            "⚠️ محدودیت‌ها:\n"
            "• فقط دستورات SELECT مجاز هستند\n"
            "• فقط می‌توانید از جدول‌های بالا استفاده کنید\n"
            "• دستورات INSERT, UPDATE, DELETE, DROP, CREATE, ALTER ممنوع هستند\n"
            "• سایر جدول‌ها غیرقابل دسترسی هستند\n\n"
            "💻 لطفاً یک کوئری SELECT معتبر ارسال کنید:",
            reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True, resize_keyboard=True)
        )
        return
    
    try:
        with engine.begin() as conn:
            result = conn.execute(text(sql_text))
            rows = result.fetchall()
            
            # ذخیره خروجی برای ارسال احتمالی به مدرس
            output_data = {
                "columns": list(result.keys()),
                "rows": [list(row) for row in rows[:100]],  # محدودیت برای جلوگیری از حجم زیاد
                "total_rows": len(rows)
            }
            context.user_data["last_output"] = json.dumps(output_data, default=str)
            
            if rows:
                columns = result.keys()
                
                result_message = "✅ نتایج اجرای کوئری:\n\n"
                result_message += "┌" + "─" * 50 + "┐\n"
                
                header = "│ " + " | ".join(str(col)[:15].ljust(15) for col in columns) + " │"
                result_message += header + "\n"
                result_message += "├" + "─" * 50 + "┤\n"
                
                for i, row in enumerate(rows[:10]):
                    row_str = "│ " + " | ".join(str(val)[:15].ljust(15) for val in row) + " │"
                    result_message += row_str + "\n"
                
                result_message += "└" + "─" * 50 + "┘\n\n"
                
                if len(rows) > 10:
                    result_message += f"📊 نمایش 10 ردیف اول از {len(rows)} ردیف\n\n"
                
            else:
                result_message = "✅ کوئری با موفقیت اجرا شد اما هیچ نتیجه‌ای بازنگشت.\n\n"
            
            # اضافه کردن گزینه ارسال به مدرس
            result_message += "📤 آیا می‌خواهید این کوئری را برای بررسی به مدرس ارسال کنید?"
            
            # ایجاد کیبورد با گزینه‌های جدید
            keyboard = [
                ["✅ بله، ارسال به مدرس"],
                ["❌ خیر، فقط نمایش"],
                ["🔙 بازگشت به منو اصلی"]
            ]
            
            update.message.reply_text(
                result_message,
                reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
            )
            
            # تغییر state برای مدیریت پاسخ کاربر
            user_state[chat_id] = "waiting_teacher_submission_decision"
            
    except Exception as e:
        error_message = f"❌ خطا در اجرای کوئری:\n\n{str(e)}\n\n"
        error_message += "💻 لطفاً کوئری خود را بررسی و مجدداً ارسال کنید:"
        
        update.message.reply_text(
            error_message,
            reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True, resize_keyboard=True)
        )
        user_state[chat_id] = "waiting_classroom_sql"

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
