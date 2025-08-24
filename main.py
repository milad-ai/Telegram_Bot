import os
import re
from telegram import Update, Document
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
user_state = {}

# ==================== تمرین جاری ====================
CURRENT_HW = "hw01"  # فقط یک بار مشخص می‌شود

welcome_text = (
    "🎓 خوش آمدید به ربات تصحیح SQL 🎓\n\n"
    "این ربات مخصوص دانشجویان درس پایگاه داده ترم ۱۴۰۴–۱۴۰۵ دانشگاه شهید بهشتی، دانشکده ریاضی است.\n\n"
    "ابتدا نام خود را وارد کنید، سپس شماره دانشجویی، و در نهایت فایل یا متن SQL خود را ارسال کنید تا بررسی و تصحیح شود.\n\n"
    "📚 موفق باشید!"
)

sql_guide_text = (
    f"✅ حالا SQL خود را ارسال کنید یا فایل .sql بفرستید.\n\n"
    "📌 نکات مهم:\n"
    f"1️⃣ شماره تمرین باید در بالای فایل مشخص شود، مثلا: -- {CURRENT_HW}\n"
    "2️⃣ هر سوال با یک کامنت مشخص می‌شود: # number 1, # number 2 و ...\n"
    "3️⃣ ترتیب اجرای Query ها مهم نیست؛ فقط خروجی با جدول مرجع مطابقت داشته باشد.\n"
    "4️⃣ می‌توانید متن SQL را مستقیم بفرستید یا یک فایل .sql ارسال کنید.\n\n"
    "💡 نمونه SQL مجاز:\n"
    "```sql\n"
    "-- hw01\n"
    "# number 1\n"
    "SELECT id, name, grade FROM students WHERE grade >= 18;\n\n"
    "# number 2\n"
    "SELECT COUNT(*) AS student_count FROM students WHERE grade >= 18;\n\n"
    "# number 3\n"
    "SELECT name FROM students WHERE grade < 18;\n"
    "```"
)

# ==================== توابع ====================
def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    update.message.reply_text(welcome_text)
    user_state[chat_id] = "waiting_name"
    update.message.reply_text("لطفاً نام خود را وارد کنید:")

def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text.strip()

    # دریافت نام
    if user_state.get(chat_id) == "waiting_name":
        context.user_data["name"] = text
        user_state[chat_id] = "waiting_student_id"
        update.message.reply_text("نام ثبت شد. لطفاً شماره دانشجویی خود را وارد کنید:")

    # دریافت شماره دانشجویی
    elif user_state.get(chat_id) == "waiting_student_id":
        context.user_data["student_id"] = text
        user_state[chat_id] = "waiting_sql"
        update.message.reply_text(sql_guide_text, parse_mode='Markdown')

    # دریافت متن SQL
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

    # جدا کردن Queryها بر اساس کامنت # number X
    queries = re.split(r"#\s*number\s*\d+", sql_text, flags=re.IGNORECASE)
    queries = [q.strip() for q in queries if q.strip()]

    student_id = context.user_data["student_id"]
    name = context.user_data["name"]
    correct_count = 0

    with engine.connect() as conn:
        for i, student_query in enumerate(queries):
            reference_table = f"{CURRENT_HW}_q{i+1}_reference"
            try:
                student_result = conn.execute(text(student_query)).mappings().all()
                reference_result = conn.execute(text(f"SELECT * FROM {reference_table}")).mappings().all()

                # مقایسه مقادیر فقط، بدون توجه به ترتیب ردیف و نام ستون
                student_values = [tuple(row.values()) for row in student_result]
                reference_values = [tuple(row.values()) for row in reference_result]

                if sorted(student_values) == sorted(reference_values):
                    correct_count += 1
            except Exception as e:
                print(f"Error executing query {i+1}: {e}")

        # ایجاد جدول نتایج در صورت نبود
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
            {"student_id": student_id, "name": name, "hw": CURRENT_HW, "correct_count": correct_count}
        )

    update.message.reply_text(
        f"✅ تصحیح انجام شد! {correct_count}/{len(queries)} Query درست است.\n\n"
        "اکنون می‌توانید تمرین بعدی را ارسال کنید؛ نیازی به وارد کردن نام یا شماره دانشجویی دوباره نیست."
    )

    # آماده برای تمرین بعدی
    user_state[chat_id] = "waiting_sql"

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
