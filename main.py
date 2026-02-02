import os
import telebot
import google.generativeai as genai

# --- AYARLAR ---
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- YAPAY ZEKA AYARLARI ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Merhaba! Modelleri kontrol etmek için /modeller yaz.")

@bot.message_handler(commands=['modeller'])
def list_models(message):
    bot.reply_to(message, "🔍 Google'a soruluyor, lütfen bekle...")
    
    try:
        model_list = []
        # Google'daki tüm modelleri tara
        for m in genai.list_models():
            # Sadece içerik üretebilen (generateContent) modelleri al
            if 'generateContent' in m.supported_generation_methods:
                model_list.append(m.name)
        
        if model_list:
            # Listeyi alt alta yazıp gönder
            response = "✅ İŞTE KULLANABİLECEĞİN MODELLER:\n\n" + "\n".join(model_list)
            bot.reply_to(message, response)
        else:
            bot.reply_to(message, "❌ Hiçbir model bulunamadı! API Anahtarında veya Bölgede sorun olabilir.")
            
    except Exception as e:
        bot.reply_to(message, f"❌ HATA OLUŞTU:\n{str(e)}")

print("Dedektif Bot Çalışıyor...")
bot.polling()
