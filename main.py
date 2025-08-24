import os
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from flask import Flask
from threading import Thread

TOKEN = os.environ.get("BOT_TOKEN")


majors = [["علوم کامپیوتر"], ["آمار"]]


user_state = {}


def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    user_state[chat_id] = "waiting_major"
    reply_markup = ReplyKeyboardMarkup(majors, one_time_keyboard=True)
    update.message.reply_text(
        "سلام! لطفاً رشته خود را انتخاب کنید:", 
        reply_markup=reply_markup
    )

def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text

    if user_state.get(chat_id) == "waiting_major":
        if text in ["علوم کامپیوتر", "آمار"]:
            user_state[chat_id] = "waiting_hw"
            context.user_data["major"] = text
            update.message.reply_text(
                f"رشته {text} انتخاب شد. حالا شماره تمرین را وارد کنید (مثلاً HW03):",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            update.message.reply_text("لطفاً یکی از گزینه‌های منو را انتخاب کنید.")
    
    elif user_state.get(chat_id) == "waiting_hw":
        context.user_data["hw"] = text
        update.message.reply_text(
            f"شماره تمرین شما {text} ثبت شد. فعلاً دیتابیس فعال نیست، بعداً بررسی می‌کنیم."
        )

        user_state[chat_id] = None

# ======== راه‌اندازی ربات ========
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
updater.start_polling()


app = Flask('')

@app.route('/')
def home():
    return "ربات تلگرام فعال است ✅"

def run():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

Thread(target=run).start()
updater.idle()
