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
W, H = 720, 1280

# --- SABİT ETİKETLER ---
FIXED_HASHTAGS = "#horror #shorts #scary #creepy #mystery #scarystories #urbanlegends #creepypasta #viral #fyp"

# --- TEMİZLİK ---
def clean_start():
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except: pass

# --- AI İÇERİK (V15 İLE AYNI - PROMPT MÜKEMMEL) ---
def get_content(topic):
    models = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-flash-latest", "gemini-2.5-flash"]
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    # Prompt V15 ile aynı (Çünkü metin tarafı kusursuz)
    prompt = (
        f"You are a viral horror shorts director. Write a script about '{topic}'. "
        "Strictly follow this format using '|||' as separator:\n"
        "SHORT TITLE (Max 5 words) ||| PERSONAL HOOK (Max 8 words) ||| SEO DESCRIPTION ||| NARRATION SCRIPT (50-60 words) ||| keyword1, keyword2, keyword3, keyword4, keyword5\n\n"
        "CRITICAL RULES:\n"
        "1. LENGTH: STRICTLY 50-60 words. Must fit in 28 seconds.\n"
        "2. STYLE: Ultra-concise. Drop articles (the, a, an). Example: 'I hear clicks', not 'I hear the clicks'.\n"
        "3. STRUCTURE: Max 8 words per sentence. Easy to read subtitles.\n"
        "4. POV: First person ('I'). No visual notes.\n"
        "5. ENDING: Sudden physical pain or shock (e.g., 'It smashed my hand').\n"
        "6. PACING: Fast action. No long descriptions."
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
                    
                    if len(parts) >= 5:
                        data = {
                            "title": parts[0].strip(),
                            "hook": parts[1].strip(),
                            "description": parts[2].strip(),
                            "script": parts[3].strip(),
                            "keywords": [k.strip() for k in parts[4].split(",")]
                        }
                        print(f"✅ İçerik alındı ({model})")
                        return data
        except: continue

    return None

# --- MEDYA OLUŞTURMA ---
async def generate_resources(content):
    script = content["script"]
    keywords = content["keywords"]
    
    # Ses: +0% Hız, -5Hz Pitch
    communicate = edge_tts.Communicate(script, "en-US-ChristopherNeural", rate="+0%", pitch="-5Hz")
    await communicate.save("voice.mp3")
    audio = AudioFileClip("voice.mp3")
    
    headers = {"Authorization": PEXELS_API_KEY}
    paths = []
    used_links = set()
    
    required_clips = int(audio.duration / 2.0) + 5 # Biraz daha fazla klip çekelim
    search_terms = keywords * 4
    random.shuffle(search_terms)

    for q in search_terms:
        if len(paths) >= required_clips: break
        try:
            # Geniş arama havuzu
            query_enhanced = f"{q} horror scary dark cinematic pov suspense mystery"
            url = f"https://api.pexels.com/videos/search?query={query_enhanced}&per_page=8&orientation=portrait"
            data = requests.get(url, headers=headers, timeout=10).json()
            
            for v in data.get("videos", []):
                if len(paths) >= required_clips: break
                
                video_url = v.get("url")
                if video_url in used_links: continue
                
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
                    if c.duration > 1.0:
                        paths.append(path)
                        used_links.add(video_url)
                    c.close()
                except:
                    if os.path.exists(path): os.remove(path)
        except: continue
        
    return paths, audio

# --- GÖRSEL EFEKTLER VE MANİPÜLASYON (YENİ!) ---
def cold_horror_grade(image):
    img_f = image.astype(float)
    gray = np.mean(img_f, axis=2, keepdims=True)
    # Renkleri her seferinde biraz rastgele solduralım (Çeşitlilik için)
    sat_factor = random.uniform(0.3, 0.5) 
    desaturated = img_f * sat_factor + gray * (1 - sat_factor)
    
    # Hafif Yeşil veya Mavi tint (Rastgele)
    if random.random() > 0.5:
        tint = np.array([0.9, 1.0, 1.1]) # Mavi
    else:
        tint = np.array([0.9, 1.05, 0.9]) # Pis Yeşil (Matrix/Saw havası)
        
    cold_img = desaturated * tint
    return np.clip(cold_img, 0, 255).astype(np.uint8)

def apply_processing(clip, duration):
    # 1. Rastgele Başlangıç (Videonun farklı yerini kullanır)
    if clip.duration > duration:
        start = random.uniform(0, clip.duration - duration)
        clip = clip.subclip(start, start + duration)
    
    # 2. Hız Manipülasyonu (%80 - %120 arası)
    speed_factor = random.uniform(0.8, 1.2)
    clip = clip.fx(vfx.speedx, speed_factor)
    
    # 3. Mirror Efekti (Ters Çevirme - %50 şans)
    if random.random() > 0.5:
        clip = clip.fx(vfx.mirror_x)
    
    # Kadrajlama (9:16)
    target_ratio = W / H
    if clip.w / clip.h > target_ratio:
        clip = clip.resize(height=H)
        clip = clip.crop(x1=clip.w/2 - W/2, width=W, height=H)
    else:
        clip = clip.resize(width=W)
        clip = clip.crop(y1=clip.h/2 - H/2, width=W, height=H)
        
    # 4. Renk Efekti
    clip = clip.fx(vfx.lum_contrast, contrast=0.2)
    clip = clip.fl_image(cold_horror_grade)
    
    # 5. Dinamik Zoom (Bazen ileri, bazen geri)
    zoom_dir = random.choice([0.02, -0.01]) # + İleri, - Geri
    clip = clip.resize(lambda t: 1 + zoom_dir * t).set_position(('center', 'center'))
    
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
                dur = random.uniform(2.0, 2.8)
                processed = apply_processing(c, dur)
                clips.append(processed)
                cur_dur += processed.duration
            except: continue

        if not clips: return None

        final = concatenate_videoclips(clips, method="compose").set_audio(audio)
        if final.duration > audio.duration:
            final = final.subclip(0, audio.duration)
        
        out = "horror_remix_v16.mp4"
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
        
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\nRemix Modu Aktif (Görsel Çeşitlilik)...")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ İçerik oluşturulamadı.", message.chat.id, msg.message_id)
            return

        bot.edit_message_text(f"🎬 {content['title']}\n🔄 Mirror, Speed & Color Remix uygulanıyor...\n⏳ Render...", message.chat.id, msg.message_id)

        path = build_video(content)
        
        if path and os.path.exists(path):
            caption_text = (
                f"🪝 **HOOK:**\n{content['hook']}\n\n"
                f"🎬 **Başlık:**\n{content['title']}\n\n"
                f"📝 **Hikaye:**\n{content['script']}\n\n"
                f"🏷️ **Açıklama:**\n{content['description']}\n\n"
                f"#️⃣ **Etiketler:**\n{FIXED_HASHTAGS}"
            )
            
            if len(caption_text) > 1000: caption_text = caption_text[:1000]
            
            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=caption_text)
        else:
            bot.edit_message_text("❌ Video render edilemedi.", message.chat.id, msg.message_id)
            
    except Exception as e:
        bot.reply_to(message, str(e))

if __name__ == "__main__":
    clean_start()
    bot.polling(non_stop=True)
