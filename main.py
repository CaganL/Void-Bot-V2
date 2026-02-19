import os
import telebot
import requests

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "ErXwobaYiN019PkySvjV") 

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

# --- SABİT ETİKETLER ---
FIXED_HASHTAGS = "#horror #shorts #scary #creepy #mystery #fyp"

# --- GEMINI: SENARYO OLUŞTURMA ---
def get_content(topic):
    # En hızlı modelleri seçtik
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    safety_settings = [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"}]

    base_prompt = (
        f"You are a VICTIM describing a FATAL physical trauma in a '{topic}'. "
        "Strictly follow this format using '|||' as separator:\n"
        "CLICKBAIT TITLE ||| PUNCHY HOOK (Sensory POV) ||| SEO DESCRIPTION ||| NARRATION SCRIPT (45-55 WORDS) ||| VISUAL_SCENES_LIST ||| MAIN_LOCATION (1 Word) ||| 3_SEARCH_VARIANTS ||| #tags\n\n"
        "RULES (PRO MODE):\n"
        "1. NO STORYTELLING. No 'ran away', no 'screamed'.\n"
        "2. ENDING: Immediate system failure (e.g. 'Spine severed').\n"
        "3. STYLE: Cold, Clinical."
    )
    
    for current_model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json={"contents": [{"parts": [{"text": base_prompt}]}], "safetySettings": safety_settings}, timeout=20)
            if r.status_code == 200:
                parts = r.json()['candidates'][0]['content']['parts'][0]['text'].split("|||")
                if len(parts) >= 8:
                    return {
                        "title": parts[0].strip(),
                        "hook": parts[1].strip(),
                        "script": parts[3].strip(),
                        "tags": parts[7].strip()
                    }
        except: continue
    return None

# --- SES MOTORU: ELEVENLABS ---
def generate_elevenlabs_audio(text, filename):
    if not ELEVENLABS_API_KEY: 
        print("❌ ElevenLabs API Anahtarı eksik!", flush=True)
        return False
        
    print("🎙️ ElevenLabs ses üretiyor...", flush=True)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": ELEVENLABS_API_KEY}
    
    # Text parametresi ElevenLabs'e gidiyor
    data = {"text": text, "model_id": "eleven_turbo_v2_5", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
    
    try:
        r = requests.post(url, json=data, headers=headers, timeout=30)
        if r.status_code == 200:
            with open(filename, 'wb') as f: f.write(r.content)
            print("✅ Ses başarıyla oluşturuldu.", flush=True)
            return True
        else:
            print(f"❌ ElevenLabs Hatası: {r.status_code} - {r.text}", flush=True)
            return False
    except Exception as e: 
        print(f"❌ ElevenLabs Bağlantı Hatası: {e}", flush=True)
        return False

# --- TELEGRAM BOT KOMUTLARI ---
@bot.message_handler(commands=["horror", "video"])
def handle(message):
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary story"
        
        print(f"\n--- YENİ TALEP: {topic} ---", flush=True)
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\n📝 Senaryo yazılıyor (Şimşek Modu)...")
        
        # 1. Senaryoyu Al
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ İçerik üretilemedi. (Gemini reddetti veya hata oluştu)", message.chat.id, msg.message_id)
            return

        bot.edit_message_text(f"🎬 **{content['title']}**\n🎙️ ElevenLabs stüdyosunda seslendiriliyor...", message.chat.id, msg.message_id)

        # 2. Hook ve Script'i birleştir (Araya "..." koyarak nefes payı bırakıyoruz)
        full_audio_text = f"{content['hook']} ... {content['script']}"
        audio_filename = "final_voice.mp3"

        # Eski kalıntıları temizle
        if os.path.exists(audio_filename): os.remove(audio_filename)

        # 3. Sesi Üret ve Gönder
        if generate_elevenlabs_audio(full_audio_text, audio_filename):
            final_tags = f"{FIXED_HASHTAGS} {content['tags']}"
            caption_text = (
                f"🪝 **HOOK:**\n{content['hook']}\n\n"
                f"🎬 **BAŞLIK:**\n{content['title']}\n\n"
                f"📝 **HİKAYE:**\n{content['script']}\n\n"
                f"#️⃣ **ETİKETLER:**\n{final_tags}"
            )
            # Metin sınırını koru
            if len(caption_text) > 1000: caption_text = caption_text[:1000]

            with open(audio_filename, "rb") as audio:
                # Videoyu değil, direkt dinlenebilir Ses (Audio) formatında gönderiyoruz
                bot.send_audio(
                    message.chat.id, 
                    audio, 
                    caption=caption_text, 
                    title=content['title'], 
                    performer="SUI Horror"
                )
            
            # İşlem bitince bilgi mesajını sil ve temizlik yap
            bot.delete_message(message.chat.id, msg.message_id)
            os.remove(audio_filename)
            print("✅ Ses dosyası Telegram'a başarıyla gönderildi.", flush=True)
            
        else:
            bot.edit_message_text("❌ Ses üretilemedi. (ElevenLabs Hatası)", message.chat.id, msg.message_id)
            print("❌ Süreç tamamlanamadı.", flush=True)
            
    except Exception as e:
        bot.reply_to(message, f"Kritik Hata: {e}")
        print(f"❌ Kritik Bot Hatası: {e}", flush=True)

if __name__ == "__main__":
    print("Bot başlatılıyor... ⚡ ŞİMŞEK MODU (Sadece Ses) Aktif!", flush=True)
    bot.polling(non_stop=True)
