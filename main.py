import os
import telebot
import requests
import random
import json
import time
import numpy as np
import textwrap
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip,
    concatenate_videoclips
)
import asyncio
import edge_tts

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# YouTube Shorts için çözünürlük
W, H = 1080, 1920
FPS = 30

# --- FONT ---
def get_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(font_path, "wb") as f:
                    f.write(r.content)
        except:
            pass
    return font_path

# --- TTS (edge-tts async) ---
async def generate_tts(text, out="voice.mp3", voice="en-US-GuyNeural"):
    communicate = edge_tts.Communicate(text, voice)
    try:
        if os.path.exists(out):
            os.remove(out)
        await communicate.save(out)
    except Exception as e:
        print(f"TTS Hatası: {e}")

# --- İÇERİK ÜRETİCİ (SENİN LİSTENLE GÜNCELLENMİŞ) ---
def get_content(topic):
    # Senin hesabında kesin var olan modeller (Sırasıyla deneyecek)
    models_to_try = [
        "gemini-2.0-flash-lite",  # En hızlı ve ekonomik (Önce bunu dener)
        "gemini-2.0-flash",       # Standart
        "gemini-2.5-flash",       # Güncel güçlü model
        "gemini-exp-1206"         # Deneysel yedek
    ]

    prompt = (
        f"You are a professional YouTube Shorts creator. Create a viral scary story about '{topic}'. "
        "Output ONLY a valid JSON object with the following keys:\n"
        "- 'script': The scary story text (Minimum 120 words, simple English, engaging hook).\n"
        "- 'title': A clickbait title for the video.\n"
        "- 'description': A short engaging description for YouTube.\n"
        "- 'hashtags': A string of 5-10 popular hashtags.\n"
        "Do not write anything else, just the JSON."
    )
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for model in models_to_try:
        # API URL'si
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        print(f"🔄 Model deneniyor: {model}...")

        try:
            r = requests.post(url, json=payload, timeout=30)
            
            if r.status_code == 200:
                print(f"✅ Başarılı Model: {model}")
                data = r.json()
                raw_text = data['candidates'][0]['content']['parts'][0]['text']
                raw_text = raw_text.replace("```json", "").replace("```", "").strip()
                result = json.loads(raw_text)
                return result
            
            elif r.status_code == 429:
                print(f"⚠️ Kota Dolu ({model}). Diğer modele geçiliyor...")
                time.sleep(2) # Hızlıca diğerine geçsin
                continue 
            
            elif r.status_code == 404:
                print(f"❌ Model Bulunamadı ({model}). Diğerine geçiliyor...")
                continue
            
            else:
                print(f"⚠️ API Hatası: {r.status_code} - {r.text}")
                time.sleep(1)
                
        except Exception as e:
            print(f"Bağlantı Hatası ({model}): {e}")
            time.sleep(1)

    # Fallback (Hiçbir model çalışmazsa)
    print("❌ Tüm modeller başarısız oldu, yedek hikaye devreye giriyor.")
    return {
        "script": "I looked at my phone screen in the dark room. It showed my face, illuminated by the blue light. But wait. In the reflection of my glasses, I saw something standing behind me. I froze. I didn't want to turn around. Slowly, I tilted the phone to see the corner of the room. It was empty. I sighed with relief and put the phone down. Then, a cold whisper touched my ear: You should have looked up.",
        "title": "Don't Look Up 😱",
        "description": "A short horror story that will keep you awake.",
        "hashtags": "#horror #scary #shorts #creepy"
    }

# --- VIDEO BUL ---
def get_videos(total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = ["dark atmosphere", "creepy shadow", "abandoned place", "horror night", "foggy forest"]
    random.shuffle(queries)

    paths = []
    current = 0
    i = 0

    for q in queries:
        if current >= total_duration:
            break

        url = f"https://api.pexels.com/videos/search?query={q}&per_page=5&orientation=portrait"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200: continue
            data = r.json().get("videos", [])
        except:
            continue

        for v in data:
            if current >= total_duration:
                break
            
            video_files = v.get("video_files", [])
            if not video_files: continue
            
            link = max(video_files, key=lambda x: x["height"])["link"]
            path = f"clip_{i}.mp4"
            i += 1

            try:
                content = requests.get(link, timeout=20).content
                with open(path, "wb") as f:
                    f.write(content)
                
                clip = VideoFileClip(path)
                if clip.duration > 1:
                    current += clip.duration
                    paths.append(path)
                clip.close()
            except:
                pass

    return paths

# --- ALTYAZI ---
def make_subtitles(text, duration):
    font_path = get_font()
    try:
        font = ImageFont.truetype(font_path, 60)
    except:
        font = ImageFont.load_default()

    words = text.split()
    chunks = []
    temp = []
    for w in words:
        temp.append(w)
        if len(temp) >= 2:
            chunks.append(" ".join(temp))
            temp = []
    if temp:
        chunks.append(" ".join(temp))

    if not chunks: return None

    per = duration / len(chunks)
    clips = []

    for ch in chunks:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        wrapped = "\n".join(textwrap.wrap(ch.upper(), 15))
        bbox = draw.textbbox((0, 0), wrapped, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        x = (W - tw) // 2
        y = int(H * 0.70)

        draw.rectangle([x-20, y-20, x+tw+20, y+th+20], fill=(0,0,0,160))
        draw.text((x, y), wrapped, font=font, fill="white", align="center")

        clips.append(ImageClip(np.array(img)).set_duration(per))

    return concatenate_videoclips(clips, method="compose")

# --- CLIP DÜZELT ---
def prepare_clip(path):
    try:
        c = VideoFileClip(path)
        c = c.without_audio()
        
        if c.w / c.h > W / H:
            c = c.resize(height=H)
            c = c.crop(x_center=c.w/2, width=W, height=H)
        else:
            c = c.resize(width=W)
            c = c.crop(y_center=c.h/2, width=W, height=H)
            
        return c
    except:
        return None

# --- MONTAJ ---
def build_video(content_data):
    script = content_data["script"]
    
    # 1. Ses
    asyncio.run(generate_tts(script, "voice.mp3"))
    if not os.path.exists("voice.mp3"):
        return None
        
    audio = AudioFileClip("voice.mp3")
    
    # 2. Video
    paths = get_videos(audio.duration)
    if not paths:
        audio.close()
        return None

    clips = []
    for p in paths:
        c = prepare_clip(p)
        if c:
            clips.append(c)

    if not clips:
        audio.close()
        return None

    # 3. Birleştirme
    main = concatenate_videoclips(clips, method="compose")

    if main.duration < audio.duration:
        main = main.loop(duration=audio.duration)
    else:
        main = main.subclip(0, audio.duration)

    main = main.set_audio(audio)

    # 4. Altyazı
    subs = make_subtitles(script, main.duration)
    final = CompositeVideoClip([main, subs], size=(W, H)) if subs else main

    out = "final_video.mp4"
    final.write_videofile(
        out,
        codec="libx264",
        audio_codec="aac",
        fps=FPS,
        threads=2,
        preset="ultrafast"
    )

    for c in clips: c.close()
    audio.close()
    main.close()
    final.close()
    
    for p in paths:
        if os.path.exists(p): os.remove(p)

    return out

# --- TELEGRAM ---
@bot.message_handler(commands=["video"])
def handle_video(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Bir konu yaz: /video ghost")
        return

    topic = args[1]
    bot.reply_to(message, "🎬 Video hazırlanıyor, lütfen bekle...")

    content = get_content(topic)
    
    path = build_video(content)

    if path and os.path.exists(path):
        caption_text = (
            f"🎬 **{content['title']}**\n\n"
            f"{content['description']}\n\n"
            f"{content['hashtags']}"
        )
        try:
            with open(path, "rb") as v:
                bot.send_video(
                    message.chat.id, 
                    v, 
                    caption=caption_text, 
                    parse_mode="Markdown"
                )
        except Exception as e:
            bot.reply_to(message, f"Video gönderilemedi: {e}")
    else:
        bot.reply_to(message, "❌ Video oluşturulamadı.")

print("Bot aktif...")
bot.polling(non_stop=True)

