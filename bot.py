import json
import os
import time
import requests
from datetime import datetime
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== ЧИТАЕМ ПЕРЕМЕННЫЕ ИЗ ОКРУЖЕНИЯ (BotHost) ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
TON_WALLET = os.getenv("TON_WALLET", "UQBfJnAtUHg7mSRnrgUkzwnxhbChOhrIDnW8t1vi4gtk5Pzk")
PRICE_USDT = int(os.getenv("PRICE_USDT", "5"))
TOTAL_FACES = int(os.getenv("TOTAL_FACES", "504"))

# Проверка, что токен задан
if not BOT_TOKEN:
    raise Exception("❌ BOT_TOKEN не задан! Добавь переменную окружения BOT_TOKEN в настройках BotHost")

DATA_FILE = "faces_data.json"
PENDING_FILE = "pending.json"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ========== РАБОТА С ДАННЫМИ ==========
def load_faces():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    else:
        faces = []
        for i in range(1, TOTAL_FACES + 1):
            faces.append({"number": i, "sold": False, "owner": "", "date": ""})
        return faces

def save_faces(faces):
    with open(DATA_FILE, "w") as f:
        json.dump(f, f, indent=2)

def load_pending():
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, "r") as f:
            return json.load(f)
    return {}

def save_pending(pending):
    with open(PENDING_FILE, "w") as f:
        json.dump(pending, f, indent=2)

faces = load_faces()
pending_payments = load_pending()

# ========== ПРОВЕРКА ТРАНЗАКЦИЙ ==========
def check_transaction(comment):
    try:
        url = f"https://toncenter.com/api/v2/getTransactions?address={TON_WALLET}&limit=30"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("ok"):
            for tx in data.get("result", []):
                msg = tx.get("in_msg", {})
                tx_comment = msg.get("message", "")
                if tx_comment and tx_comment.strip() == comment:
                    return True
    except Exception as e:
        print(f"Ошибка проверки: {e}")
    return False

# ========== КОМАНДЫ БОТА ==========
@bot.message_handler(commands=['start'])
def cmd_start(message):
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("buy_"):
        try:
            face_number = int(args[1].split("_")[1])
        except:
            bot.reply_to(message, "❌ Ошибка: неверный формат ссылки")
            return
        
        face = next((f for f in faces if f["number"] == face_number), None)
        
        if not face:
            bot.reply_to(message, "❌ Грань не найдена!")
            return
        
        if face["sold"]:
            bot.reply_to(message, f"❌ Грань #{face_number} уже продана!")
            return
        
        comment = f"FACE{face_number}_{message.from_user.id}_{int(time.time())}"
        
        pending_payments[str(message.from_user.id)] = {
            "face_number": face_number,
            "comment": comment,
            "created_at": time.time()
        }
        save_pending(pending_payments)
        
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("✅ Я ОПЛАТИЛ", callback_data=f"check_{face_number}_{comment}"))
        
        bot.send_message(
            message.chat.id,
            f"🎟️ ПОКУПКА ГРАНИ #{face_number}\n\n"
            f"💰 Цена: {PRICE_USDT} USDT (TON)\n\n"
            f"📤 Кошелёк:\n`{TON_WALLET}`\n\n"
            f"📝 Комментарий к переводу:\n`{comment}`\n\n"
            f"После оплаты нажмите кнопку ниже. Бот проверит транзакцию автоматически.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        bot.reply_to(
            message,
            "🏆 КРИПТО-СФЕРА\n\n"
            "Перейдите на сайт, выберите свободную грань и нажмите «Купить».\n\n"
            "Ссылку на сайт скоро получите."
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_"))
def handle_payment_check(call):
    parts = call.data.split("_")
    face_number = int(parts[1])
    expected_comment = "_".join(parts[2:])
    user_id = str(call.from_user.id)
    
    if user_id not in pending_payments:
        bot.edit_message_text(
            "❌ Сессия оплаты устарела. Выберите грань заново на сайте.",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id)
        return
    
    payment = pending_payments[user_id]
    if payment["face_number"] != face_number:
        bot.answer_callback_query(call.id, "Ошибка: несоответствие грани", show_alert=True)
        return
    
    bot.edit_message_text(
        "🔄 Проверяем транзакцию... Подождите.",
        call.message.chat.id,
        call.message.message_id
    )
    
    paid = check_transaction(expected_comment)
    
    if paid:
        face = next((f for f in faces if f["number"] == face_number), None)
        if face and not face["sold"]:
            face["sold"] = True
            face["owner"] = f"user_{call.from_user.id}"
            face["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_faces(faces)
            del pending_payments[user_id]
            save_pending(pending_payments)
            
            bot.edit_message_text(
                f"✅ ПОЗДРАВЛЯЮ!\n\nГрань #{face_number} теперь ваша!\n\nСпасибо за покупку! 🚀",
                call.message.chat.id,
                call.message.message_id
            )
        else:
            bot.edit_message_text(
                "❌ К сожалению, эту грань уже кто-то купил раньше.",
                call.message.chat.id,
                call.message.message_id
            )
    else:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🔄 Проверить снова", callback_data=f"check_{face_number}_{expected_comment}"))
        
        bot.edit_message_text(
            f"⏳ Платёж не найден.\n\n"
            f"Убедитесь, что вы отправили ровно {PRICE_USDT} USDT на кошелёк\n"
            f"`{TON_WALLET}`\n\n"
            f"с комментарием:\n`{expected_comment}`\n\n"
            f"Транзакции могут обрабатываться до 5 минут.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    
    bot.answer_callback_query(call.id)

# ========== API ДЛЯ САЙТА ==========
@app.route('/api/faces', methods=['GET'])
def get_faces():
    return jsonify(faces)

@app.route('/')
def index():
    return jsonify({"status": "ok", "bot": "CryptoSphere Bot is running"})

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # Запускаем бота в отдельном потоке (для Flask)
    import threading
    threading.Thread(target=bot.polling, daemon=True).start()
    # Запускаем Flask на порту, который даёт BotHost
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
