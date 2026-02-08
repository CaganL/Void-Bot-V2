import os
import telebot
import requests
import random
import json
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

# --- TEMİZLİK ---
def clean_start():
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
        print("Bot başlatılıyor...")
    except: pass

# --- AI İÇERİK (YEDEK YOK - SADECE YENİ) ---
def get_content(topic):
    # Farklı modelleri sırayla dener
    models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    
    prompt = (
        f"You are a narrator for a viral horror YouTube Shorts channel. Write a script about '{topic}'. "
        "STRICT RULES: "
        "1. NO INTRO, NO OUTRO. Start directly with the story. "
        "2. Length: MUST be between 90 and 110 words (Targeting 30-35 seconds). "
        "3. Flow: Use short sentences to reduce pauses. "
        "4. Visuals: Provide 6 dark, scary, atmospheric keywords. "
        "Output ONLY JSON: "
        "{'script': 'Story text...', 'hook': 'First shocking sentence', 'keywords': ['k1', 'k2', 'k3', 'k4', 'k5', 'k6']}"
    )
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    # 3 Kez dene, başaramazsan HATA ver (Eski senaryo kullanma)
    for attempt in range(3):
        for model in models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                r = requests.post(url, json=payload, timeout=20)
                if r.status_code == 200:
                    text = r.json()['candidates'][0]['content']['parts'][0]['text']
                    clean_text = text.replace("```json", "").replace("```", "").strip()
                    data = json.loads(clean_text)
                    return data
            except:
                continue
        time.sleep(1) # Hata olursa 1 saniye bekle tekrar dene

    return None # Başarısız olursa None döner

# --- SES VE VİDEO ---
async def generate_resources(content):
    script = content["script"]
    keywords = content["keywords"]
    
    # --- SES AYARLARI (KORKU MODU) ---
    # Voice: Christopher (Daha hikaye odaklı/tok ses)
    # Rate: +10% (Boşlukları kapatmak ve akıcı olmak için hızlandı)
    # Pitch: -5Hz (Daha kalın ve gergin ses)
    communicate = edge_tts.Communicate(script, "en-US-ChristopherNeural", rate="+10%", pitch="-5Hz")
    
    await communicate.save("voice.mp3")
    audio = AudioFileClip("voice.mp3")
    
    headers = {"Authorization": PEXELS_API_KEY}
    paths = []
    
    # Ses süresini dolduracak kadar klip + yedek
    required_clips = int(audio.duration / 2.5) + 4
    
    # Kelimeleri karıştır
    search_terms = keywords * 3
    random.shuffle(search_terms)

    for q in search_terms:
        if len(paths) >= required_clips: break
        
        try:
            # Sadece karanlık/dikey videolar
            url = f"https://api.pexels.com/videos/search?query={q} dark horror scary creepy&per_page=4&orientation=portrait"
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
                    if c.duration > 1.0: # 1 saniyeden uzunsa al
                        paths.append(path)
                    c.close()
                except:
                    if os.path.exists(path): os.remove(path)
        except: continue
        
    return paths, audio

# --- EFEKTLER ---
def apply_effects(clip, duration):
    # Rastgele bir kesit al
    if clip.duration > duration:
        start = random.uniform(0, clip.duration - duration)
        clip = clip.subclip(start, start + duration)
    
    # 9:16 Kırpma
    target_ratio = W / H
    if clip.w / clip.h > target_ratio:
        clip = clip.resize(height=H)
        clip = clip.crop(x1=clip.w/2 - W/2, width=W, height=H)
    else:
        clip = clip.resize(width=W)
        clip = clip.crop(y1=clip.h/2 - H/2, width=W, height=H)
        
    # Zoom Efekti (%5 büyüme - İzleyiciyi içine çeker)
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
                # Klipler arası süre: 2.0sn ile 3.5sn arası (Hızlı kurgu)
                dur = random.uniform(2.0, 3.5)
                
                processed = apply_effects(c, dur)
                clips.append(processed)
                cur_dur += processed.duration
            except: continue

        if not clips: return None

        final = concatenate_videoclips(clips, method="compose").set_audio(audio)
        
        # Tam ses süresinde bitir
        if final.duration > audio.duration:
            final = final.subclip(0, audio.duration)
        
        out = "horror_final.mp4"
        # Render Kalitesi (Preset veryfast = Hızlı render)
        final.write_videofile(out, fps=24, codec="libx264", preset="veryfast", bitrate="4500k", audio_bitrate="192k", threads=4, logger=None)
        
        audio.close()
        for c in clips: c.close()
        for p in paths: 
            if os.path.exists(p): os.remove(p)
        return out
    except Exception as e:
        print(e)
        return None

# --- TELEGRAM ---
@bot.message_handler(commands=["horror", "video"])
def handle(message):
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary facts"
        
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\nSenaryo yazılıyor... (Yedek yok, tamamen yeni!)")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ Senaryo oluşturulamadı. Lütfen tekrar dene.", message.chat.id, msg.message_id)
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
    bot.polling(non_stop=True)
