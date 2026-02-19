import os
import telebot
import requests

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

# Ses: Callum (Hırıltılı, Gergin, Psikolojik Gerilime Uygun)
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "N2lVS1w4EtoT3dr4eOWO") 

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

# --- SABİT ETİKETLER ---
FIXED_HASHTAGS = "#horror #shorts #scary #creepy #mystery #fyp"

# --- GEMINI: SENARYO OLUŞTURMA (YOUTUBE PARA KAZANMA DOSTU) ---
def get_content(topic):
    # En hızlı modelleri seçtik
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    safety_settings = [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"}]

    base_prompt = (
        f"You are experiencing a terrifying, mysterious encounter related to '{topic}'. "
        "Strictly follow this format using '|||' as separator:\n"
        "CLICKBAIT TITLE ||| PUNCHY HOOK (MAX 8 WORDS, Sensory POV) ||| SEO DESCRIPTION ||| NARRATION SCRIPT (55-65 WORDS) ||| VISUAL_SCENES_LIST ||| MAIN_LOCATION (1 Word) ||| 3_SEARCH_VARIANTS ||| #tags\n\n"
        "RULES (YOUTUBE SAFE & VIRAL):\n"
        "1. NO GORE, NO BLOOD, NO MEDICAL TERMS. (Never use words like: organs, ruptured, severed, spine, bleeding, fatal, death).\n"
        "2. PSYCHOLOGICAL DREAD: Build fear through senses. Unnatural silence, heavy pressure, freezing temperatures, moving shadows, a feeling of being watched.\n"
        "3. IMPLIED ENDING: End with an eerie realization, sudden darkness, or a chilling final thought instead of physical death (e.g., 'My body stopped responding as the lights went out.', 'The whispering stopped, but I wasn't alone.').\n"
        "4. STRICT RULE: DO NOT repeat the Hook in the Narration Script. The script must continue directly from where the hook left off."
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
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\n📝 Senaryo yazılıyor (Psikolojik Gerilim + Callum)...")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ İçerik üretilemedi. (Gemini reddetti veya hata oluştu)", message.chat.id, msg.message_id)
            return

        bot.edit_message_text(f"🎬 **{content['title']}**\n🎙️ ElevenLabs stüdyosunda Callum seslendiriyor...", message.chat.id, msg.message_id)

        # Nefes payı eklendi
        full_audio_text = f"{content['hook']} ... {content['script']}"
        audio_filename = "final_voice.mp3"

        if os.path.exists(audio_filename): os.remove(audio_filename)

        if generate_elevenlabs_audio(full_audio_text, audio_filename):
            final_tags = f"{FIXED_HASHTAGS} {content['tags']}"
            caption_text = (
                f"🪝 **HOOK:**\n{content['hook']}\n\n"
                f"🎬 **BAŞLIK:**\n{content['title']}\n\n"
                f"📝 **HİKAYE:**\n{content['script']}\n\n"
                f"#️⃣ **ETİKETLER:**\n{final_tags}"
            )
            
            if len(caption_text) > 1000: caption_text = caption_text[:1000]

            with open(audio_filename, "rb") as audio:
                bot.send_audio(
                    message.chat.id, 
                    audio, 
                    caption=caption_text, 
                    title=content['title'], 
                    performer="SUI Horror - Callum"
                )
            
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
    print("Bot başlatılıyor... ⚡ YOUTUBE DOSTU (Callum) Sürümü Aktif!", flush=True)
    bot.polling(non_stop=True)
