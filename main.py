import os
import telebot
import requests
import random
import json
import time
import asyncio
import edge_tts
from moviepy.editor import (
    VideoFileClip, AudioFileClip, concatenate_videoclips, vfx
)

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
W, H = 1080, 1920

# --- KRİTİK DÜZELTME: BAŞLANGIÇ TEMİZLİĞİ ---
def clean_start():
    """Eski bağlantıları ve takılı kalan oturumları temizler."""
    print("🧹 Eski bağlantılar temizleniyor...")
    try:
        # 1. Mevcut Webhook'u sil (Çakışmayı önler)
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
        print("✅ Webhook silindi.")
        
        # 2. Biraz bekle ki Telegram API nefes alsın
        time.sleep(2)
        print("🤖 Bot başlatılıyor...")
    except Exception as e:
        print(f"⚠️ Temizlik uyarısı: {e}")

# --- AI İÇERİK (HOOK ODAKLI & KISA) ---
def get_content(topic):
    models = ["gemini-2.0-flash", "gemini-1.5-flash"]
    
    # 25-35 saniye için kelime sayısı: ~60-75 kelime.
    prompt = (
        f"You are a master of horror shorts. Create a terrifying script about '{topic}'. "
        "1. START with a 'KILLER HOOK' (a shocking 1-sentence statement or question). "
        "2. The story must be fast-paced, dark, and twisty. "
        "3. Total length: STRICTLY 60 to 75 words (for 25-30s video). "
        "4. 'visual_keywords' must be dark, atmospheric nouns (e.g., 'abandoned hallway', 'shadow', 'skull'). "
        "Output ONLY JSON: "
        "{'script': 'Full text including hook', 'hook_text_only': 'Just the hook sentence', 'title': 'Title', 'visual_keywords': ['k1', 'k2', 'k3', 'k4', 'k5', 'k6']}"
    )
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                text = r.json()['candidates'][0]['content']['parts'][0]['text']
                # Json temizliği
                clean_text = text.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_text)
                return data
        except: continue

    # Fallback (Yedek)
    return {
        "script": "Do you know who is watching you right now? Look closely at the shadows. They say if you stare long enough, they stare back.",
        "hook_text_only": "Do you know who is watching you right now?",
        "title": "Don't Look",
        "visual_keywords": ["dark eye", "shadow", "fear"]
    }

# --- MEDYA VE SES ---
async def generate_resources(content):
    script = content["script"]
    keywords = content["visual_keywords"]
    
    # Seslendirme: Pitch -2Hz (Daha kalın/korkunç)
    communicate = edge_tts.Communicate(script, "en-US-GuyNeural", rate="+8%", pitch="-2Hz")
    await communicate.save("voice.mp3")
    audio = AudioFileClip("voice.mp3")
    
    headers = {"Authorization": PEXELS_API_KEY}
    paths = []
    
    required_clips = int(audio.duration / 2.5) + 3 
    extended_keywords = keywords * 3
    random.shuffle(extended_keywords)

    for q in extended_keywords:
        if len(paths) >= required_clips: break
        
        # FİLTRE: Sadece karanlık/korku videoları
        dark_query = f"{q} dark horror scary creepy night vertical"
        
        try:
            url = f"https://api.pexels.com/videos/search?query={dark_query}&per_page=3&orientation=portrait"
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
                    if c.duration > 1.5:
                        paths.append(path)
                    c.close()
                except:
                    if os.path.exists(path): os.remove(path)
        except: continue
        
    return paths, audio

# --- EFEKTLER (ZOOM & CROP) ---
def apply_horror_effects(clip, duration=3):
    # Süre kesimi
    if clip.duration > duration:
        start = random.uniform(0, clip.duration - duration)
        clip = clip.subclip(start, start + duration)
    
    # 9:16 Kırpma
    target_ratio = W / H
    clip_ratio = clip.w / clip.h
    
    if clip_ratio > target_ratio:
        clip = clip.resize(height=H)
        clip = clip.crop(x1=clip.w/2 - W/2, width=W, height=H)
    else:
        clip = clip.resize(width=W)
        clip = clip.crop(y1=clip.h/2 - H/2, width=W, height=H)
        
    # ZOOM EFFECT (Yavaşça yaklaşma)
    clip = clip.resize(lambda t: 1 + 0.04 * t) 
    clip = clip.set_position(('center', 'center'))
    
    return clip

# --- MONTAJ ---
def build_video(content):
    try:
        paths, audio = asyncio.run(generate_resources(content))
        if not paths: return None
            
        clips = []
        current_duration = 0
        
        for p in paths:
            if current_duration >= audio.duration: break
            try:
                c = VideoFileClip(p).without_audio()
                # Hızlı geçişler (2.0 - 3.5 sn)
                clip_len = random.uniform(2.0, 3.5)
                processed_clip = apply_horror_effects(c, duration=clip_len)
                clips.append(processed_clip)
                current_duration += processed_clip.duration
            except: continue

        if not clips: return None

        main_clip = concatenate_videoclips(clips, method="compose")
        main_clip = main_clip.set_audio(audio)
        
        if main_clip.duration > audio.duration:
            main_clip = main_clip.subclip(0, audio.duration)
        
        final_video = main_clip 
        out = "final_horror.mp4"
        
        final_video.write_videofile(
            out, fps=24, codec="libx264", preset="veryfast", 
            bitrate="4000k", audio_bitrate="192k", threads=4, logger=None
        )
        
        audio.close()
        for c in clips: c.close()
        for p in paths: 
            if os.path.exists(p): os.remove(p)
            
        return out
    except Exception as e:
        print(f"Genel Hata: {e}")
        return None

# --- TELEGRAM ---
@bot.message_handler(commands=["horror"])
def handle_video(message):
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary fact"
        
        bot.reply_to(message, f"💀 Konu: **{topic}**\n🕯️ Karanlık arşivler taranıyor, gerilim yükleniyor...")
        
        content = get_content(topic)
        path = build_video(content)
        
        if path and os.path.exists(path):
            caption_text = (
                f"⚠️ **{content['hook_text_only'].upper()}**\n\n"
                f"{content['script']}\n\n"
                "#horror #scary #creepy #mystery #shorts"
            )
            if len(caption_text) > 1000: caption_text = caption_text[:1000]

            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=caption_text, parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Korku videosu oluşturulamadı.")
            
    except Exception as e:
        bot.reply_to(message, f"Hata: {e}")

# --- ÇALIŞTIRMA ---
if __name__ == "__main__":
    clean_start() # Temizliği yap
    bot.polling(non_stop=True) # Botu başlat
