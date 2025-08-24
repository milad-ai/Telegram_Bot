
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
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

# لیست chat_id های ادمین (ابتدا خالی)
admin_chat_ids = set()

if not TOKEN or not DB_URI:
    raise ValueError("BOT_TOKEN and DB_URI must be set!")

if not ADMIN_PASSWORD:
    print("⚠️  WARNING: ADMIN_PASSWORD is not set! Admin functionality will be disabled.")

engine = create_engine(DB_URI)

majors = [["علوم کامپیوتر"], ["آمار"]]
hw_numbers = [["3", "4", "5", "6"]]

user_state = {}

welcome_text = (
    "خوش آمدید! این ربات برای درس پایگاه داده دانشجویان در نیم‌سال اول ۱۴۰۵–۱۴۰۴ "
    "دانشگاه شهید بهشتی، دانشکده ریاضی طراحی شده است.\n\n"
    "📋 راهنمای استفاده:\n"
    "1️⃣ رشته خود را انتخاب کنید\n"
    "2️⃣ نام و نام خانوادگی و شماره دانشجویی را وارد کنید\n"
    "3️⃣ شماره تمرین را انتخاب کنید (3، 4، 5، 6)\n"
    "4️⃣ کد SQL خود را ارسال کنید (متن یا فایل .sql)\n\n"
    "⚠️  قبل از هر سوال حتماً کامنت # number X بگذارید\n\n"
    "• از `;` در پایان هر query استفاده کنید\n"
    "• فاصله‌ها و enter های اضافی مشکلی ندارند\n"
    "• هر شماره دانشجویی حداکثر ۱۰ بار می‌تواند هر تمرین را ارسال کند\n\n"
    "📝 نمونه فرمت صحیح:\n"
 
    "# number 1\n"
    "SELECT id, name, grade\n"
    "FROM students\n"
    "WHERE grade >= 15;\n\n"
    "# number 2\n"
    "SELECT COUNT(*) as student_count\n"
    "FROM students\n"
    "WHERE grade >= 15;\n\n"
    "# number 3\n"
    "SELECT name\n"
    "FROM students\n"
    "WHERE grade < 10;\n"
  

)

def get_persian_datetime():
    """تاریخ و ساعت فعلی را به وقت تهران و به فارسی برمی‌گرداند"""
    # تنظیم timezone تهران
    tehran_tz = pytz.timezone('Asia/Tehran')
    now = datetime.now(tehran_tz)
    
    persian_date = jdatetime.datetime.fromgregorian(datetime=now)
    
    # نام روزهای هفته به فارسی
    persian_weekdays = {
        0: 'شنبه',
        1: 'یکشنبه', 
        2: 'دوشنبه',
        3: 'سه‌شنبه',
        4: 'چهارشنبه',
        5: 'پنج‌شنبه',
        6: 'جمعه'
    }
    
    # نام ماه‌های فارسی
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

def get_main_menu():
    """منوی اصلی را برمی‌گرداند"""
    return ReplyKeyboardMarkup([["تمرین جدید"], ["پایان"]], one_time_keyboard=True)

def get_hw_selection_menu():
    """منوی انتخاب تمرین با دکمه بازگشت را برمی‌گرداند"""
    hw_with_back = hw_numbers + [["🔙 بازگشت به منو اصلی"]]
    return ReplyKeyboardMarkup(hw_with_back, one_time_keyboard=True)

def is_admin(chat_id: int) -> bool:
    """بررسی می‌کند آیا کاربر ادمین است یا نه"""
    return chat_id in admin_chat_ids

def add_admin(chat_id: int):
    """اضافه کردن ادمین جدید"""
    admin_chat_ids.add(chat_id)

def get_admin_menu():
    """منوی ادمین را برمی‌گرداند"""
    return ReplyKeyboardMarkup([
        ["📊 آمار کلی", "📈 آمار بر اساس رشته"],
        ["📋 لیست دانشجویان", "📁 خروجی Excel"],
        ["🔙 بازگشت به منو اصلی"]
    ], one_time_keyboard=True)

# ==================== توابع ====================
def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    
    # بررسی ادمین بودن
    if is_admin(chat_id):
        update.message.reply_text("🔐 سلام مدیر محترم!\n\n" + welcome_text)
        user_state[chat_id] = "admin_mode"
        reply_markup = ReplyKeyboardMarkup([
            ["👤 ورود به عنوان دانشجو", "🛠 پنل مدیریت"]
        ], one_time_keyboard=True)
        update.message.reply_text("نوع ورود خود را انتخاب کنید:", reply_markup=reply_markup)
    else:
        update.message.reply_text(welcome_text)
        
        # نمایش دکمه مدیر فقط اگر رمز تنظیم شده باشد
        if ADMIN_PASSWORD:
            reply_markup = ReplyKeyboardMarkup([
                ["👤 دانشجو", "🔐 مدیر"]
            ], one_time_keyboard=True)
            update.message.reply_text("شما کیستید؟", reply_markup=reply_markup)
            user_state[chat_id] = "choosing_role"
        else:
            # اگر رمز ادمین تنظیم نشده، مستقیم به منوی دانشجو برو
            user_state[chat_id] = "waiting_major"
            reply_markup = ReplyKeyboardMarkup(majors, one_time_keyboard=True)
            update.message.reply_text("لطفاً رشته خود را انتخاب کنید:", reply_markup=reply_markup)

def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text

    # بررسی دکمه بازگشت به منو اصلی
    if text == "🔙 بازگشت به منو اصلی":
        user_state[chat_id] = "completed"
        update.message.reply_text("بازگشت به منو اصلی:", reply_markup=get_main_menu())
        return

    # انتخاب نقش کاربر
    if user_state.get(chat_id) == "choosing_role":
        if text == "👤 دانشجو":
            user_state[chat_id] = "waiting_major"
            reply_markup = ReplyKeyboardMarkup(majors, one_time_keyboard=True)
            update.message.reply_text("لطفاً رشته خود را انتخاب کنید:", reply_markup=reply_markup)
        elif text == "🔐 مدیر":
            user_state[chat_id] = "waiting_admin_password"
            update.message.reply_text("🔐 لطفاً رمز مدیریت را وارد کنید:", reply_markup=ReplyKeyboardRemove())
        return

    # ورود رمز ادمین
    if user_state.get(chat_id) == "waiting_admin_password":
        if ADMIN_PASSWORD and text == ADMIN_PASSWORD:
            add_admin(chat_id)
            user_state[chat_id] = "admin_mode"
            reply_markup = ReplyKeyboardMarkup([
                ["👤 ورود به عنوان دانشجو", "🛠 پنل مدیریت"]
            ], one_time_keyboard=True)
            update.message.reply_text("✅ رمز صحیح است! خوش آمدید مدیر محترم.", reply_markup=reply_markup)
        elif not ADMIN_PASSWORD:
            update.message.reply_text("❌ رمز ادمین تنظیم نشده است. لطفاً با مدیر سیستم تماس بگیرید.")
            user_state[chat_id] = "waiting_major"
            reply_markup = ReplyKeyboardMarkup(majors, one_time_keyboard=True)
            update.message.reply_text("لطفاً رشته خود را انتخاب کنید:", reply_markup=reply_markup)
        else:
            update.message.reply_text("❌ رمز اشتباه است. لطفاً دوباره تلاش کنید یا /start را بزنید.")
        return

    # مدیریت حالت ادمین
    if user_state.get(chat_id) == "admin_mode":
        if text == "👤 ورود به عنوان دانشجو":
            user_state[chat_id] = "waiting_major"
            reply_markup = ReplyKeyboardMarkup(majors, one_time_keyboard=True)
            update.message.reply_text("لطفاً رشته خود را انتخاب کنید:", reply_markup=reply_markup)
        elif text == "🛠 پنل مدیریت":
            user_state[chat_id] = "admin_panel"
            update.message.reply_text("🛠 پنل مدیریت:", reply_markup=get_admin_menu())
        return

    # مدیریت پنل ادمین
    if user_state.get(chat_id) == "admin_panel":
        if text == "📊 آمار کلی":
            show_general_stats(update)
        elif text == "📈 آمار بر اساس رشته":
            show_major_stats(update)
        elif text == "📋 لیست دانشجویان":
            show_student_list(update)
        elif text == "📁 خروجی Excel":
            export_to_text(update)
        elif text == "🔙 بازگشت به منو اصلی":
            user_state[chat_id] = "completed"
            update.message.reply_text("بازگشت به منو اصلی:", reply_markup=get_main_menu())
        return

    if user_state.get(chat_id) == "waiting_major":
        if text in ["علوم کامپیوتر", "آمار"]:
            context.user_data["major"] = text
            user_state[chat_id] = "waiting_name"
            update.message.reply_text("رشته انتخاب شد. لطفاً نام خود را وارد کنید:", reply_markup=ReplyKeyboardRemove())
        else:
            update.message.reply_text("لطفاً یکی از گزینه‌های منو را انتخاب کنید.")

    elif user_state.get(chat_id) == "waiting_name":
        context.user_data["name"] = text.strip()
        user_state[chat_id] = "waiting_student_id"
        update.message.reply_text("لطفاً شماره دانشجویی خود را وارد کنید:")

    elif user_state.get(chat_id) == "waiting_student_id":
        context.user_data["student_id"] = text.strip()
        user_state[chat_id] = "waiting_hw"
        reply_markup = get_hw_selection_menu()
        update.message.reply_text("اطلاعات شما ثبت شد. شماره تمرین را انتخاب کنید:", reply_markup=reply_markup)

    elif user_state.get(chat_id) == "waiting_hw":
        if text == "🔙 بازگشت به منو اصلی":
            user_state[chat_id] = "completed"
            update.message.reply_text("بازگشت به منو اصلی:", reply_markup=get_main_menu())
            return
            
        if text in ["3", "4", "5", "6"]:
            student_id = context.user_data["student_id"]
            hw = text
            
            # بررسی تعداد ارسال‌های قبلی
            submission_count = get_submission_count(student_id, hw)
            
            if submission_count >= 10:
                update.message.reply_text(
                    f"❌ شما قبلاً ۱۰ بار تمرین {hw} را ارسال کرده‌اید و حق ارسال مجدد ندارید.\n"
                    "لطفاً تمرین دیگری انتخاب کنید:",
                    reply_markup=get_hw_selection_menu()
                )
                return
            
            context.user_data["hw"] = hw
            user_state[chat_id] = "waiting_sql"
            remaining_attempts = 10 - submission_count
            update.message.reply_text(
                f"تمرین {hw} انتخاب شد.\n"
                f"📊 تعداد ارسال‌های باقی‌مانده: {remaining_attempts}\n\n"
                "لطفاً SQL خود را ارسال کنید یا فایل .sql بفرستید:",
                reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True)
            )
        else:
            update.message.reply_text("لطفاً شماره تمرین معتبر انتخاب کنید.")

    elif user_state.get(chat_id) == "waiting_sql":
        if text == "🔙 بازگشت به منو اصلی":
            user_state[chat_id] = "completed"
            update.message.reply_text("بازگشت به منو اصلی:", reply_markup=get_main_menu())
            return
            
        sql_text = text
        process_sql(update, context, sql_text)

    elif user_state.get(chat_id) == "completed":
        if text == "تمرین جدید":
            user_state[chat_id] = "waiting_hw"
            reply_markup = get_hw_selection_menu()
            update.message.reply_text("شماره تمرین جدید را انتخاب کنید:", reply_markup=reply_markup)
        elif text == "پایان":
            # بررسی ادمین بودن برای نمایش پنل مدیریت
            if is_admin(chat_id):
                reply_markup = ReplyKeyboardMarkup([
                    ["👤 ورود به عنوان دانشجو", "🛠 پنل مدیریت"],
                    ["❌ خروج کامل"]
                ], one_time_keyboard=True)
                update.message.reply_text("گزینه مورد نظر را انتخاب کنید:", reply_markup=reply_markup)
                user_state[chat_id] = "admin_mode"
            else:
                update.message.reply_text("متشکرم از استفاده! برای شروع دوباره /start را بزنید.", 
                                        reply_markup=get_main_menu())
        elif text == "❌ خروج کامل":
            update.message.reply_text("متشکرم از استفاده! برای شروع دوباره /start را بزنید.", 
                                    reply_markup=ReplyKeyboardRemove())
        else:
            update.message.reply_text("لطفاً یکی از گزینه‌های منو را انتخاب کنید.", 
                                    reply_markup=get_main_menu())

# ==================== دریافت فایل SQL ====================
def handle_document(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    if user_state.get(chat_id) != "waiting_sql":
        update.message.reply_text("لطفاً مراحل را از /start دنبال کنید.")
        return

    document: Document = update.message.document
    if not document.file_name.endswith(".sql"):
        update.message.reply_text("لطفاً یک فایل معتبر .sql ارسال کنید.\n\nیا برای بازگشت به منو اصلی دکمه زیر را بزنید:",
                                reply_markup=ReplyKeyboardMarkup([["🔙 بازگشت به منو اصلی"]], one_time_keyboard=True))
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
    major = context.user_data["major"]

    # بررسی مجدد محدودیت ارسال
    submission_count = get_submission_count(student_id, hw)
    if submission_count >= 10:
        update.message.reply_text(
            f"❌ شما قبلاً ۱۰ بار تمرین {hw} را ارسال کرده‌اید و حق ارسال مجدد ندارید.",
            reply_markup=get_main_menu()
        )
        user_state[chat_id] = "completed"
        return

    correct_count = 0
    incorrect_questions = []  # لیست سوال‌های اشتباه

    with engine.begin() as conn:
        for i, student_query in enumerate(queries):
            question_number = i + 1
            try:
                student_rows = conn.execute(text(student_query)).fetchall()
                reference_table = f"hw{hw}_q{question_number}_reference"
                reference_rows = conn.execute(text(f"SELECT * FROM {reference_table}")).fetchall()
                
                if set(student_rows) == set(reference_rows):
                    correct_count += 1
                else:
                    incorrect_questions.append(question_number)
                    
            except Exception as e:
                print(f"Error executing query {question_number}: {e}")
                incorrect_questions.append(question_number)

        # ایجاد جدول اگر وجود نداشته باشد (با فیلد major اضافه شده)
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

        # درج داده‌ها (با major)
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

    # آماده‌سازی پیام نتیجه (با اطلاعات دانشجو و تاریخ/ساعت)
    persian_date, persian_time = get_persian_datetime()
    
    result_message = f"✅ تصحیح انجام شد!\n\n"
    result_message += f"📅 تاریخ تصحیح: {persian_date}\n"
    result_message += f"🕐 ساعت تصحیح: {persian_time}\n\n"
    result_message += f"👤 دانشجو: {name}\n"
    result_message += f"🆔 شماره دانشجویی: {student_id}\n"
    result_message += f"📚 رشته: {major}\n"
    result_message += f"📝 تمرین: {hw}\n\n"
    result_message += f"📊 نتیجه: {correct_count}/{len(queries)} سوال درست است.\n\n"
    
    # نمایش سوال‌های اشتباه
    if incorrect_questions:
        result_message += "❌ سوال‌های اشتباه: " + ", ".join(map(str, incorrect_questions)) + "\n\n"
    else:
        result_message += "🎉 تبریک! تمام سوال‌ها درست است!\n\n"
    
    # نمایش تعداد ارسال‌های باقی‌مانده
    new_submission_count = submission_count + 1
    remaining_attempts = 10 - new_submission_count
    result_message += f"📈 تعداد ارسال‌های انجام شده: {new_submission_count}/10\n"
    result_message += f"📊 ارسال‌های باقی‌مانده: {remaining_attempts}\n\n"
    
    if remaining_attempts == 0:
        result_message += "⚠️ این آخرین ارسال شما برای این تمرین بود.\n\n"
    
    # ارسال نتیجه و آماده‌سازی برای منوی بعدی
    result_message += "آیا می‌خواهید تمرین جدیدی ثبت کنید؟"
    
    update.message.reply_text(result_message, reply_markup=get_main_menu())
    user_state[chat_id] = "completed"

# ==================== توابع پنل ادمین ====================
def show_general_stats(update: Update):
    """نمایش آمار کلی"""
    try:
        with engine.begin() as conn:
            # تعداد کل دانشجویان
            total_students = conn.execute(text("""
                SELECT COUNT(DISTINCT student_id) FROM student_results
            """)).fetchone()[0]
            
            # تعداد کل ارسال‌ها
            total_submissions = conn.execute(text("""
                SELECT COUNT(*) FROM student_results
            """)).fetchone()[0]
            
            # میانگین نمرات
            avg_score = conn.execute(text("""
                SELECT ROUND(AVG(CAST(correct_count AS FLOAT)), 2) FROM student_results
            """)).fetchone()[0]
            
            # آمار هر تمرین
            hw_stats = conn.execute(text("""
                SELECT hw, COUNT(*) as submissions, ROUND(AVG(CAST(correct_count AS FLOAT)), 2) as avg_score
                FROM student_results 
                GROUP BY hw 
                ORDER BY hw
            """)).fetchall()
            
            # بهترین نمرات
            top_scores = conn.execute(text("""
                SELECT name, student_id, major, hw, correct_count
                FROM student_results 
                WHERE correct_count = (SELECT MAX(correct_count) FROM student_results)
                LIMIT 5
            """)).fetchall()

        persian_date, persian_time = get_persian_datetime()
        
        message = f"📊 **گزارش آماری کلی**\n"
        message += f"📅 تاریخ: {persian_date}\n"
        message += f"🕐 ساعت: {persian_time}\n\n"
        
        message += f"👥 تعداد کل دانشجویان: {total_students}\n"
        message += f"📝 تعداد کل ارسال‌ها: {total_submissions}\n"
        message += f"📊 میانگین نمرات: {avg_score or 0}\n\n"
        
        message += "📈 **آمار هر تمرین:**\n"
        for hw, submissions, avg in hw_stats:
            message += f"تمرین {hw}: {submissions} ارسال، میانگین: {avg or 0}\n"
        
        message += f"\n🏆 **بهترین نمرات:**\n"
        for name, student_id, major, hw, score in top_scores:
            message += f"{name} ({student_id}) - {major} - تمرین {hw}: {score}\n"
            
        update.message.reply_text(message, reply_markup=get_admin_menu())
        
    except Exception as e:
        update.message.reply_text(f"❌ خطا در دریافت آمار: {str(e)}", reply_markup=get_admin_menu())

def show_major_stats(update: Update):
    """نمایش آمار بر اساس رشته"""
    try:
        with engine.begin() as conn:
            # آمار هر رشته
            major_stats = conn.execute(text("""
                SELECT 
                    major,
                    COUNT(DISTINCT student_id) as students,
                    COUNT(*) as submissions,
                    ROUND(AVG(CAST(correct_count AS FLOAT)), 2) as avg_score,
                    MAX(correct_count) as max_score,
                    MIN(correct_count) as min_score
                FROM student_results 
                GROUP BY major 
                ORDER BY major
            """)).fetchall()
            
            # آمار هر رشته برای هر تمرین
            detailed_stats = conn.execute(text("""
                SELECT 
                    major, hw,
                    COUNT(*) as submissions,
                    ROUND(AVG(CAST(correct_count AS FLOAT)), 2) as avg_score
                FROM student_results 
                GROUP BY major, hw 
                ORDER BY major, hw
            """)).fetchall()

        persian_date, persian_time = get_persian_datetime()
        
        message = f"📈 **گزارش آماری بر اساس رشته**\n"
        message += f"📅 تاریخ: {persian_date}\n\n"
        
        message += "📊 **آمار کلی هر رشته:**\n"
        for major, students, submissions, avg, max_score, min_score in major_stats:
            message += f"\n🎓 **{major}:**\n"
            message += f"  👥 دانشجویان: {students}\n"
            message += f"  📝 ارسال‌ها: {submissions}\n"
            message += f"  📊 میانگین: {avg or 0}\n"
            message += f"  🔝 بالاترین: {max_score}\n"
            message += f"  🔻 پایین‌ترین: {min_score}\n"
        
        message += f"\n📋 **آمار تفصیلی هر تمرین:**\n"
        current_major = ""
        for major, hw, submissions, avg in detailed_stats:
            if major != current_major:
                message += f"\n🎓 **{major}:**\n"
                current_major = major
            message += f"  تمرین {hw}: {submissions} ارسال، میانگین: {avg or 0}\n"
            
        update.message.reply_text(message, reply_markup=get_admin_menu())
        
    except Exception as e:
        update.message.reply_text(f"❌ خطا در دریافت آمار رشته: {str(e)}", reply_markup=get_admin_menu())

def show_student_list(update: Update):
    """نمایش لیست دانشجویان"""
    try:
        with engine.begin() as conn:
            students = conn.execute(text("""
                SELECT 
                    student_id, name, major,
                    COUNT(*) as total_submissions,
                    ROUND(AVG(CAST(correct_count AS FLOAT)), 2) as avg_score,
                    MAX(submission_time) as last_submission
                FROM student_results 
                GROUP BY student_id, name, major 
                ORDER BY major, name
            """)).fetchall()

        if not students:
            update.message.reply_text("📋 هنوز هیچ دانشجویی ثبت‌نام نکرده است.", reply_markup=get_admin_menu())
            return

        message = f"📋 **لیست دانشجویان** ({len(students)} نفر)\n\n"
        
        current_major = ""
        for student_id, name, major, submissions, avg, last_sub in students:
            if major != current_major:
                message += f"\n🎓 **{major}:**\n"
                current_major = major
            
            # تبدیل تاریخ آخرین ارسال
            if last_sub:
                last_date = jdatetime.datetime.fromgregorian(datetime=last_sub)
                last_formatted = f"{last_date.day}/{last_date.month}/{last_date.year}"
            else:
                last_formatted = "---"
                
            message += f"• {name} ({student_id})\n"
            message += f"  📝 {submissions} ارسال | 📊 میانگین: {avg or 0} | 📅 آخرین: {last_formatted}\n"
            
        update.message.reply_text(message, reply_markup=get_admin_menu())
        
    except Exception as e:
        update.message.reply_text(f"❌ خطا در دریافت لیست: {str(e)}", reply_markup=get_admin_menu())

def export_to_text(update: Update):
    """خروجی متنی از اطلاعات (جایگزین Excel)"""
    try:
        with engine.begin() as conn:
            all_data = conn.execute(text("""
                SELECT 
                    student_id, name, major, hw, correct_count, submission_time
                FROM student_results 
                ORDER BY major, name, submission_time
            """)).fetchall()

        if not all_data:
            update.message.reply_text("📁 هیچ داده‌ای برای خروجی وجود ندارد.", reply_markup=get_admin_menu())
            return

        persian_date, persian_time = get_persian_datetime()
        
        # ایجاد فایل متنی
        export_text = f"گزارش کامل سیستم تصحیح تمرین\n"
        export_text += f"تاریخ تهیه: {persian_date} - {persian_time}\n"
        export_text += f"تعداد رکورد: {len(all_data)}\n"
        export_text += "=" * 50 + "\n\n"
        
        current_student = ""
        for student_id, name, major, hw, score, sub_time in all_data:
            if f"{name}_{student_id}" != current_student:
                export_text += f"\n👤 {name} ({student_id}) - {major}\n"
                export_text += "-" * 30 + "\n"
                current_student = f"{name}_{student_id}"
            
            # تبدیل تاریخ
            sub_date = jdatetime.datetime.fromgregorian(datetime=sub_time)
            date_formatted = f"{sub_date.day}/{sub_date.month}/{sub_date.year} {sub_date.hour:02d}:{sub_date.minute:02d}"
            
            export_text += f"تمرین {hw}: {score} نمره | {date_formatted}\n"

        # ارسال به صورت فایل
        with open('report.txt', 'w', encoding='utf-8') as f:
            f.write(export_text)
        
        with open('report.txt', 'rb') as f:
            update.message.reply_document(
                document=f,
                filename=f'database_report_{persian_date.replace(" ", "_")}.txt',
                caption="📁 گزارش کامل سیستم"
            )
        
        os.remove('report.txt')  # پاک کردن فایل موقت
        update.message.reply_text("✅ فایل گزارش ارسال شد.", reply_markup=get_admin_menu())
        
    except Exception as e:
        update.message.reply_text(f"❌ خطا در تهیه گزارش: {str(e)}", reply_markup=get_admin_menu())

# ==================== راه‌اندازی ربات ====================
def admin_command(update: Update, context: CallbackContext):
    """دستور مخصوص ادمین"""
    chat_id = update.message.chat_id
    if is_admin(chat_id):
        user_state[chat_id] = "admin_panel"
        update.message.reply_text("🛠 پنل مدیریت:", reply_markup=get_admin_menu())
    else:
        update.message.reply_text("❌ شما دسترسی ادمین ندارید.")

def get_chat_id(update: Update, context: CallbackContext):
    """نمایش chat_id کاربر"""
    chat_id = update.message.chat_id
    user = update.message.from_user
    message = f"🆔 **اطلاعات شما:**\n"
    message += f"Chat ID: `{chat_id}`\n"
    message += f"نام: {user.first_name or 'ندارد'}\n"
    message += f"نام خانوادگی: {user.last_name or 'ندارد'}\n"
    message += f"Username: @{user.username or 'ندارد'}\n"
    message += f"وضعیت ادمین: {'✅ بله' if is_admin(chat_id) else '❌ خیر'}"
    update.message.reply_text(message, parse_mode='Markdown')

updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("admin", admin_command))
dp.add_handler(CommandHandler("chatid", get_chat_id))  # تابع موقت برای گرفتن chat_id
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
