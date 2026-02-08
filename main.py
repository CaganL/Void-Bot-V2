import os
import telebot
import requests
import random
import time
import asyncio
import edge_tts
import numpy as np
from moviepy.editor import (
    VideoFileClip, AudioFileClip, concatenate_videoclips, vfx
)

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

# 720p Çözünürlük (Performans ve Kalite Dengesi)
W, H = 720, 1280

# --- BAŞLANGIÇ TEMİZLİĞİ ---
def clean_start():
    print("🧹 Eski bağlantılar temizleniyor...")
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
        time.sleep(1)
        print("✅ Bot başlatılıyor...")
    except Exception as e:
        print(f"⚠️ Temizlik uyarısı: {e}")

# --- AI İÇERİK (BAŞLIK EKLENDİ) ---
def get_content(topic):
    models = [
        "gemini-2.5-flash-lite", 
        "gemini-2.0-flash-lite", 
        "gemini-flash-latest",
        "gemini-2.5-flash"
    ]
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    # Prompt güncellendi: Artık BAŞLIK da istiyoruz.
    prompt = (
        f"You are a master of horror shorts. Write a script about '{topic}'. "
        "Strictly follow this format using '|||' as separator:\n"
        "SHORT TITLE (Max 5 words) ||| PUNCHY HOOK (Max 1 sentence) ||| FULL STORY TEXT (90-110 words) ||| keyword1, keyword2, keyword3, keyword4, keyword5\n\n"
        "Rules:\n"
        "1. Title must be scary.\n"
        "2. Hook must be clickbait.\n"
        "3. Story must be fast-paced.\n"
        "4. Keywords must search for atmosphere (e.g., 'foggy forest', 'shadow')."
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
            
            if r.status_code == 429:
                time.sleep(2)
                continue

            if r.status_code == 200:
                response_json = r.json()
                if 'candidates' in response_json and response_json['candidates']:
                    raw_text = response_json['candidates'][0]['content']['parts'][0]['text']
                    parts = raw_text.split("|||")
                    
                    if len(parts) >= 4:
                        data = {
                            "title": parts[0].strip(),
                            "hook": parts[1].strip(),
                            "script": parts[2].strip(),
                            "keywords": [k.strip() for k in parts[3].split(",")]
                        }
                        print(f"✅ İçerik alındı ({model})")
                        return data
        except: continue

    return {
        "title": "The Mirror Trap",
        "hook": "NEVER LOOK IN THE MIRROR AT 3AM",
        "script": "You think it's just a superstition. Until you wake up thirsty in the middle of the night. You walk past the bathroom mirror. Out of the corner of your eye, your reflection blinks when you didn't. You stop. You look closely. It smiles, showing too many teeth. Don't scream. It hates loud noises.",
        "keywords": ["creepy mirror", "dark bathroom", "shadow figure", "scary face"]
    }

# --- MEDYA OLUŞTURMA (TEKRAR ÖNLEME EKLENDİ) ---
async def generate_resources(content):
    script = content["script"]
    keywords = content["keywords"]
    
    communicate = edge_tts.Communicate(script, "en-US-ChristopherNeural", rate="+10%", pitch="-5Hz")
    await communicate.save("voice.mp3")
    audio = AudioFileClip("voice.mp3")
    
    headers = {"Authorization": PEXELS_API_KEY}
    paths = []
    used_links = set() # Aynı videoyu iki kere kullanmamak için hafıza
    
    required_clips = int(audio.duration / 2.5) + 3
    search_terms = keywords * 4 # Daha fazla kelime
    random.shuffle(search_terms)

    print("🎬 Videolar aranıyor...")

    for q in search_terms:
        if len(paths) >= required_clips: break
        try:
            query_enhanced = f"{q} cinematic moody dark atmospheric horror"
            # Arama sayısını artırdık (per_page=5) ki daha çok seçenek olsun
            url = f"https://api.pexels.com/videos/search?query={query_enhanced}&per_page=5&orientation=portrait"
            data = requests.get(url, headers=headers, timeout=10).json()
            
            for v in data.get("videos", []):
                if len(paths) >= required_clips: break
                
                # --- TEKRAR KONTROLÜ ---
                video_url = v.get("url")
                if video_url in used_links:
                    continue # Bu video kullanıldıysa atla
                
                files = v.get("video_files", [])
                if not files: continue
                
                suitable = [f for f in files if f["width"] >= 600 and f["width"] < 2500]
                if not suitable: suitable = files
                link = sorted(suitable, key=lambda x: x["height"], reverse=True)[0]["link"]
                
                path = f"clip_{len(paths)}.mp4"
                with open(path, "wb") as f:
                    f.write(requests.get(link, timeout=15).content)
                
                try:
                    c = VideoFileClip(path)
                    if c.duration > 1.5:
                        paths.append(path)
                        used_links.add(video_url) # Kullanılan videoyu hafızaya kaydet
                    c.close()
                except:
                    if os.path.exists(path): os.remove(path)
        except: continue
        
    return paths, audio

# --- GÖRSEL EFEKTLER (SOĞUK & SOLUK) ---
def cold_horror_grade(image):
    img_f = image.astype(float)
    gray = np.mean(img_f, axis=2, keepdims=True)
    desaturated = img_f * 0.4 + gray * 0.6 # Biraz daha renkli (%40 renk)
    tint_matrix = np.array([0.9, 1.0, 1.1]) # Hafif mavi
    cold_img = desaturated * tint_matrix
    return np.clip(cold_img, 0, 255).astype(np.uint8)

def apply_processing(clip, duration):
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
        
    # Efektler
    clip = clip.fx(vfx.lum_contrast, contrast=0.2)
    clip = clip.fl_image(cold_horror_grade)
    
    # Hafif Zoom
    clip = clip.resize(lambda t: 1 + 0.02 * t).set_position(('center', 'center'))
    
    return clip

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
                dur = random.uniform(2.5, 4.0)
                processed = apply_processing(c, dur)
                clips.append(processed)
                cur_dur += processed.duration
            except: continue

        if not clips: return None

        final = concatenate_videoclips(clips, method="compose").set_audio(audio)
        if final.duration > audio.duration:
            final = final.subclip(0, audio.duration)
        
        out = "horror_final_v5.mp4"
        final.write_videofile(out, fps=24, codec="libx264", preset="veryfast", bitrate="3500k", audio_bitrate="128k", threads=4, logger=None)
        
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
        
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\nSenaryo hazırlanıyor... (Anti-Tekrar Modu)")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ İçerik oluşturulamadı.", message.chat.id, msg.message_id)
            return

        bot.edit_message_text(f"🎬 Başlık: {content['title']}\n🎨 Videolar seçiliyor (Benzersiz)...\n⏳ İşleniyor...", message.chat.id, msg.message_id)

        path = build_video(content)
        
        if path and os.path.exists(path):
            # İSTEDİĞİN MESAJ FORMATI
            caption_text = (
                f"🪝 **HOOK Cümlesi:**\n{content['hook']}\n\n"
                f"🎬 **Başlık:**\n{content['title']}\n\n"
                f"📝 **Videodaki Hikayenin Tamamı:**\n{content['script']}\n\n"
                f"🏷️ **Açıklama ve #:**\n#horror #shorts #scary #creepy #mystery"
            )
            
            # Mesaj çok uzunsa kes (Telegram limiti)
            if len(caption_text) > 1000: caption_text = caption_text[:1000]
            
            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=caption_text)
        else:
            bot.edit_message_text("❌ Video render edilemedi.", message.chat.id, msg.message_id)
            
    except Exception as e:
        bot.reply_to(message, str(e))

if __name__ == "__main__":
    clean_start()
    print("🚀 Bot aktif! Tekrar yok, format düzgün.")
    bot.polling(non_stop=True)
