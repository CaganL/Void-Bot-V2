import os
import telebot
import requests
import random
import time
import asyncio
import edge_tts
from moviepy.editor import (
    VideoFileClip, AudioFileClip, concatenate_videoclips
)

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
W, H = 1080, 1920

# --- BAŞLANGIÇ TEMİZLİĞİ ---
def clean_start():
    print("🧹 Eski bağlantılar temizleniyor...")
    try:
        # Webhook'u silerek çakışmaları önle
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
        time.sleep(1)
        print("✅ Bot başlatılıyor...")
    except Exception as e:
        print(f"⚠️ Temizlik uyarısı: {e}")

# --- AI İÇERİK (DÜZ METİN MODU - ASLA HATA VERMEZ) ---
def get_content(topic):
    models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    
    # Güvenlik ayarlarını tamamen kapatıyoruz
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    # JSON yerine Düz Metin istiyoruz (Daha sağlam)
    prompt = (
        f"You are a horror storyteller. Write a short script about '{topic}'. "
        "Strictly follow this format using '|||' as separator:\n"
        "HOOK SENTENCE ||| FULL STORY TEXT (90-110 words) ||| keyword1, keyword2, keyword3, keyword4, keyword5, keyword6\n\n"
        "Rules:\n"
        "1. No intro/outro text, just the content.\n"
        "2. Make it scary and viral.\n"
        "3. Keywords must be visual (e.g. dark forest, skull)."
    )
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": safety_settings
    }

    print(f"🤖 Gemini'ye soruluyor: {topic}...")

    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json=payload, timeout=20)
            
            if r.status_code == 200:
                response_json = r.json()
                if 'candidates' in response_json and response_json['candidates']:
                    raw_text = response_json['candidates'][0]['content']['parts'][0]['text']
                    
                    # Düz metni "|||" işaretlerinden bölüyoruz
                    parts = raw_text.split("|||")
                    
                    if len(parts) >= 3:
                        data = {
                            "hook": parts[0].strip(),
                            "script": parts[1].strip(),
                            "keywords": [k.strip() for k in parts[2].split(",")]
                        }
                        print(f"✅ İçerik alındı: {data['hook']}")
                        return data
                    else:
                        print(f"⚠️ Format hatası ({model}): {raw_text[:50]}...")
                else:
                    print(f"⚠️ Boş cevap ({model}) - Güvenlik filtresi olabilir.")
            else:
                print(f"❌ API Hatası ({model}): {r.status_code} - {r.text}")
                
        except Exception as e:
            print(f"Hata ({model}): {e}")
            continue

    print("❌ Tüm modeller başarısız oldu.")
    return None

# --- SES VE VİDEO ---
async def generate_resources(content):
    script = content["script"]
    keywords = content["keywords"]
    
    # Ses: Christopher (Korku tonu)
    communicate = edge_tts.Communicate(script, "en-US-ChristopherNeural", rate="+10%", pitch="-5Hz")
    await communicate.save("voice.mp3")
    audio = AudioFileClip("voice.mp3")
    
    headers = {"Authorization": PEXELS_API_KEY}
    paths = []
    
    required_clips = int(audio.duration / 2.5) + 4
    search_terms = keywords * 3
    random.shuffle(search_terms)

    print("🎬 Videolar aranıyor...")

    for q in search_terms:
        if len(paths) >= required_clips: break
        try:
            # Sadece dikey ve karanlık videolar
            url = f"https://api.pexels.com/videos/search?query={q} dark horror scary&per_page=3&orientation=portrait"
            data = requests.get(url, headers=headers, timeout=10).json()
            
            for v in data.get("videos", []):
                if len(paths) >= required_clips: break
                files = v.get("video_files", [])
                if not files: continue
                
                suitable = [f for f in files if f["width"] >= 720 and f["width"] < 2500]
                if not suitable: suitable = files
                link = sorted(suitable, key=lambda x: x["height"], reverse=True)[0]["link"]
                
                path = f"clip_{len(paths)}.mp4"
                with open(path, "wb") as f:
                    f.write(requests.get(link, timeout=15).content)
                
                try:
                    c = VideoFileClip(path)
                    if c.duration > 1.0: paths.append(path)
                    c.close()
                except:
                    if os.path.exists(path): os.remove(path)
        except: continue
        
    return paths, audio

# --- EFEKTLER ---
def apply_effects(clip, duration):
    if clip.duration > duration:
        start = random.uniform(0, clip.duration - duration)
        clip = clip.subclip(start, start + duration)
    
    target_ratio = W / H
    if clip.w / clip.h > target_ratio:
        clip = clip.resize(height=H)
        clip = clip.crop(x1=clip.w/2 - W/2, width=W, height=H)
    else:
        clip = clip.resize(width=W)
        clip = clip.crop(y1=clip.h/2 - H/2, width=W, height=H)
        
    # Zoom efekti
    return clip.resize(lambda t: 1 + 0.05 * t).set_position(('center', 'center'))

# --- MONTAJ ---
def build_video(content):
    try:
        paths, audio = asyncio.run(generate_resources(content))
        if not paths: return None
            
        clips = []
        cur_dur = 0
        
        for p in paths:
            if cur_dur >= audio.duration: break
            try:
                c = VideoFileClip(p).without_audio()
                dur = random.uniform(2.0, 3.5)
                processed = apply_effects(c, dur)
                clips.append(processed)
                cur_dur += processed.duration
            except: continue

        if not clips: return None

        final = concatenate_videoclips(clips, method="compose").set_audio(audio)
        if final.duration > audio.duration:
            final = final.subclip(0, audio.duration)
        
        out = "horror_final.mp4"
        final.write_videofile(out, fps=24, codec="libx264", preset="veryfast", bitrate="4500k", audio_bitrate="192k", threads=4, logger=None)
        
        audio.close()
        for c in clips: c.close()
        for p in paths: 
            if os.path.exists(p): os.remove(p)
        return out
    except Exception as e:
        print(f"Montaj hatası: {e}")
        return None

# --- TELEGRAM ---
@bot.message_handler(commands=["horror", "video"])
def handle(message):
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary story"
        
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\nSenaryo yazılıyor... (V3 - Text Modu)")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ Senaryo oluşturulamadı. Logları kontrol et.", message.chat.id, msg.message_id)
            return

        bot.edit_message_text(f"🎥 Senaryo hazır!\n🎙️ Seslendiriliyor: '{content['hook']}'\n⏳ Video işleniyor...", message.chat.id, msg.message_id)

        path = build_video(content)
        
        if path and os.path.exists(path):
            caption = f"⚠️ **{content['hook']}**\n\n{content['script']}\n\n#horror #shorts #scary"
            if len(caption) > 1000: caption = caption[:1000]
            
            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=caption)
        else:
            bot.edit_message_text("❌ Video render hatası.", message.chat.id, msg.message_id)
            
    except Exception as e:
        bot.reply_to(message, str(e))

if __name__ == "__main__":
    clean_start()
    print("🚀 Bot aktif! /horror komutu bekleniyor.")
    bot.polling(non_stop=True)
