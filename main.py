
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

engine = create_engine(DB_URI)

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

def get_student_info(student_id: str, password: str = None):
    """اطلاعات دانشجو را از جدول stuid دریافت می‌کند"""
    try:
        with engine.begin() as conn:
            if password is None:
                # فقط بررسی وجود شماره دانشجویی
                result = conn.execute(
                    text("SELECT name, major, pass FROM stuid WHERE student_id = :student_id"),
                    {"student_id": student_id}
                ).fetchone()
                if result:
                    return result[0], result[1], result[2]  # name, major, password
                return None, None, None
            else:
                # بررسی شماره دانشجویی و رمز عبور
                result = conn.execute(
                    text("SELECT name, major FROM stuid WHERE student_id = :student_id AND pass = :password"),
                    {"student_id": student_id, "password": password}
                ).fetchone()
                if result:
                    return result[0], result[1], None  # name, major, None
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
    return ReplyKeyboardMarkup([
        ["🚀 تمرین جدید"],
        ["🔐 تغییر رمز عبور"],
        ["🔚 پایان"]
    ], one_time_keyboard=True, resize_keyboard=True)

def get_hw_selection_menu():
    hw_with_back = [
        ["📝 تمرین 3", "📝 تمرین 4"],
        ["📝 تمرین 5", "📝 تمرین 6"],
        ["🔙 بازگشت به منو اصلی"]
    ]
    return ReplyKeyboardMarkup(hw_with_back, one_time_keyboard=True, resize_keyboard=True)

# ==================== توابع ====================

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
                f"👤 سلام {name}!\n\n"
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
            
        # استخراج شماره تمرین از متن
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
                "• رمز عبور باید حداقل 4 کاراکتر باشد\n"
                "• از ترکیب حروف و اعداد استفاده کنید\n"
                "• رمز عبور را در جای امنی نگهداری کنید",
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

# ==================== دریافت فایل SQL ====================

def handle_document(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    if user_state.get(chat_id) != "waiting_sql":
        update.message.reply_text("لطفاً مراحل را از /start دنبال کنید.")
        return
    
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

# ==================== پردازش SQL ====================

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
                # انتخاب جدول مرجع بر اساس رشته
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
    
    # پیام جدید برای ارسال ایمیل
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
