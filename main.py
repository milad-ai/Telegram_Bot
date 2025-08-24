
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
    "```sql\n"
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
    "```"

)

# ==================== توابع کمکی ====================
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

    # بررسی دکمه بازگشت به منو اصلی
    if text == "🔙 بازگشت به منو اصلی":
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
            update.message.reply_text("متشکرم از استفاده! برای شروع دوباره /start را بزنید.", 
                                    reply_markup=get_main_menu())
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

        # ایجاد جدول اگر وجود نداشته باشد
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS student_results (
                id SERIAL PRIMARY KEY,
                student_id TEXT NOT NULL,
                name TEXT NOT NULL,
                hw TEXT NOT NULL,
                correct_count INTEGER NOT NULL,
                submission_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # درج داده‌ها
        try:
            conn.execute(
                text("INSERT INTO student_results (student_id, name, hw, correct_count) VALUES (:student_id, :name, :hw, :correct_count)"),
                {"student_id": student_id, "name": name, "hw": hw, "correct_count": correct_count}
            )
            print(f"✅ Data inserted successfully for {name} ({student_id}) - HW{hw}: {correct_count} correct")
        except Exception as e:
            print(f"❌ Error inserting data: {e}")
            update.message.reply_text(f"⚠️ خطا در ذخیره‌سازی: {str(e)}")
            return

    # آماده‌سازی پیام نتیجه
    result_message = f"✅ تصحیح انجام شد!\n📊 نتیجه: {correct_count}/{len(queries)} سوال درست است.\n\n"
    
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
