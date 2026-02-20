import os
import telebot
import requests
import time

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

# --- SES KÜTÜPHANESİ ---
VOICES = {
    "david": "kaGxVtjLwllv1bi2GFag",   # Soğuk, Raporlayıcı, Tech/AI Horror (TAVSİYE EDİLEN)
    "richard": "eQIVHCAcQuAFeJps0K5l", # Ciddi, Kasvetli, Belgesel 
    "callum": "N2lVS1w4EtoT3dr4eOWO"   # Panik, Kurban 
}

# Varsayılan sesi David olarak ayarladık
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", VOICES["david"]) 

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

# --- SABİT ETİKETLER ---
FIXED_HASHTAGS = "#horror #shorts #scary #creepy #mystery #fyp"

# --- GEMINI: SENARYO OLUŞTURMA (FAZ 2: ZİHİN KIRAN PARALEL GERÇEKLİK) ---
def get_content(topic):
    models = [
        "gemini-flash-latest", 
        "gemini-2.5-flash",    
        "gemini-exp-1206"      
    ]
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]

    base_prompt = (
        f"Write a psychological horror short script about: '{topic}'. "
        "Strictly follow this exact format using '|||' as separator:\n"
        "CLICKBAIT TITLE (1st Person POV ONLY) ||| PUNCHY HOOK (MAX 6 WORDS) ||| SEO DESCRIPTION ||| NARRATION SCRIPT (55-65 WORDS) ||| VISUAL_SCENES_LIST ||| MAIN_LOCATION (1 Word) ||| 3_UNIQUE_SEARCH_VARIANTS ||| #tags (Max 3 unique tags. DO NOT use #horror, #shorts, #fyp)\n\n"
        "RULES (VIRAL SHORTS MODE - PHASE 2: MIND-BENDING + INSIDE):\n"
        "1. NO GORE, NO BLOOD. Build fear through paranoia, unnatural silence, and everyday technology.\n"
        "2. ZERO REPORTING (SHOW, DON'T TELL): DO NOT explain or narrate. Use cold, harsh, fragmented sensory facts ONLY. (e.g., 'Screen black.', 'Button jammed.', 'Cold air.').\n"
        "3. THE HOOK: Ultra-short, maximum 6 words. Immediate anomaly. (e.g., 'Connected. Nothing else was.', 'I never recorded this.').\n"
        "4. THE CLIMAX (PARADOX + PHYSICAL THREAT): DO NOT end with a generic 'something touched me'. Combine a technology/reality paradox with an immediate physical invasion. Create visual parallelism. (e.g., 'On screen, my reflection leaned into the lens. In the dark room, I felt breath on my actual ear.', 'The text said 'Look up'. The typing sound came from the ceiling.'). Break their mind at the last second.\n"
        "5. STRICT RULE: DO NOT repeat the Hook in the Narration Script. The Narration Script must contain totally new words starting right where the Hook left off.\n"
        "6. POV RULE: Both the Title and the Narration Script MUST strictly be in the 1st person ('I', 'My'). Never use 'He/She/They'."
    )
    
    for current_model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json={"contents": [{"parts": [{"text": base_prompt}]}], "safetySettings": safety_settings}, timeout=20)
            
            if r.status_code == 200:
                raw_text = r.json()['candidates'][0]['content']['parts'][0]['text']
                parts = raw_text.split("|||")
                
                if len(parts) >= 8:
                    return {
                        "title": parts[0].strip(),
                        "hook": parts[1].strip(),
                        "script": parts[3].strip(),
                        "tags": parts[7].strip()
                    }
                else:
                    print(f"⚠️ Format Hatası ({current_model}): Gemini eksik parça yolladı.", flush=True)
            
            elif r.status_code == 429:
                print(f"⏳ {current_model} Kotası Doldu! Diğer modele geçiliyor...", flush=True)
                time.sleep(2) 
                continue
                
            else:
                print(f"❌ Gemini API Hatası ({current_model}): {r.status_code} - {r.text}", flush=True)
                continue
                
        except Exception as e:
            print(f"❌ İstek Hatası ({current_model}): {e}", flush=True)
            continue
            
    return None

# --- SES MOTORU: ELEVENLABS ---
def generate_elevenlabs_audio(text, filename):
    if not ELEVENLABS_API_KEY: 
        print("❌ ElevenLabs API Anahtarı eksik!", flush=True)
        return False
        
    print("🎙️ ElevenLabs ses üretiyor...", flush=True)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": ELEVENLABS_API_KEY}
    
    data = {
        "text": text, 
        "model_id": "eleven_turbo_v2_5", 
        "voice_settings": {
            "stability": 0.45,         
            "similarity_boost": 0.85,  
            "style": 0.15              
        }
    }
    
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
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\n📝 Senaryo yazılıyor (FAZ 2: Zihin Kıran Final)...")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ İçerik üretilemedi. (Lütfen 1 dakika bekleyip tekrar deneyin).", message.chat.id, msg.message_id)
            return

        bot.edit_message_text(f"🎬 **{content['title']}**\n🎙️ ElevenLabs stüdyosunda David seslendiriyor...", message.chat.id, msg.message_id)

        # --- YAZILIMSAL MAKAS (TEKRAR ÖNLEYİCİ) ---
        hook_text = content['hook']
        script_text = content['script']
        
        if script_text.lower().startswith(hook_text.lower()):
            script_text = script_text[len(hook_text):].strip()
            script_text = script_text.lstrip(".,?! -")
            
        full_audio_text = f"{hook_text} ... {script_text}"
        
        audio_filename = "final_voice.mp3"

        if os.path.exists(audio_filename): os.remove(audio_filename)

        if generate_elevenlabs_audio(full_audio_text, audio_filename):
            final_tags = f"{FIXED_HASHTAGS} {content['tags']}"
            caption_text = (
                f"🪝 **HOOK:**\n{hook_text}\n\n"
                f"🎬 **BAŞLIK:**\n{content['title']}\n\n"
                f"📝 **HİKAYE:**\n{script_text}\n\n"
                f"#️⃣ **ETİKETLER:**\n{final_tags}"
            )
            
            if len(caption_text) > 1000: caption_text = caption_text[:1000]

            with open(audio_filename, "rb") as audio:
                bot.send_audio(
                    message.chat.id, 
                    audio, 
                    caption=caption_text, 
                    title=content['title'], 
                    performer="SUI Horror - David"
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
    print("Bot başlatılıyor... ⚡ FAZ 2 SÜRÜMÜ Aktif!", flush=True)
    bot.polling(non_stop=True)
