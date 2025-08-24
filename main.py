import os
from telegram.ext import Updater, CommandHandler
from flask import Flask
from threading import Thread

# توکن از Environment Variable
TOKEN = os.environ.get("BOT_TOKEN")

def start(update, context):
    update.message.reply_text("سلام! ربات فعال است 🚀")

updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
updater.start_polling()

# وب سرور Flask برای Keep Alive
app = Flask('')

@app.route('/')
def home():
    return "ربات تلگرام فعال است ✅"

def run():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

Thread(target=run).start()
updater.idle()
