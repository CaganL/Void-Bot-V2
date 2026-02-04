import os
import telebot
import requests
import random
import subprocess
import numpy as np
import textwrap
import time
import json
import re
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, afx, CompositeAudioClip

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY") 
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = getattr(Image, 'Resampling', Image).LANCZOS

def cleanup_files(file_list):
    for f in file_list:
        if os.path.exists(f):
            try: os.remove(f)
            except: pass

def get_safe_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path) or os.path.getsize(font_path) < 1000:
        if os.path.exists(font_path): os.remove(font_path)
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(font_path, "wb") as f: f.write(r.content)
        except: pass
    return font_path if os.path.exists(font_path) else None

# --- BELGESEL SESİ (RYAN - BRITISH) ---
def generate_tts(text, output="voice.mp3"):
    try:
        # Hız -10% (Ağırbaşlı), Perde -2Hz (Tok ses)
        subprocess.run(["edge-tts", "--voice", "en-GB-RyanNeural", "--rate=-10%", "--pitch=-2Hz", "--text", text, "--write-media", output], check=True)
        return True
    except: 
        # Eğer Ryan çalışmazsa, eski Christopher'a dön (Garanti olsun)
        try:
            subprocess.run(["edge-tts", "--voice", "en-US-ChristopherNeural", "--text", text, "--write-media", output], check=True)
            return True
        except: return False

# --- HİKAYE MOTORU (GARANTİLİ) ---
def get_script_and_metadata(topic):
    # Senin anahtarınla en uyumlu modeller
    models = ["models/gemini-1.5-flash", "models/gemini-1.5-pro"]
    
    prompt = (
        f"Write a short, dark, and mysterious storytelling script about '{topic}'.\n"
        "RULES:\n"
        "1. Start directly with a dramatic scene. No 'Did you know'.\n"
        "2. Use emotional, short sentences. Like a Netflix documentary intro.\n"
        "3. Length: 90-110 words.\n"
        "4. END the text with: KEYWORDS: term1, term2, term3\n"
    )
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
            if r.status_code == 200:
                text = r.json()['candidates'][0]['content']['parts'][0]['text']
                parts = text.split("KEYWORDS:")
                script = parts[0].strip().replace("*", "").replace("#", "")
                
                if len(parts) > 1:
                    keywords = [k.strip() for k in parts[1].split(",")]
                else:
                    keywords = [topic, "dark cinematic", "mystery"]
                
                # Sinematik eklemeler
                keywords = keywords[:3] 
                
                if len(script.split()) > 20:
                    return script, "cinematic", keywords, f"#shorts {topic}"
        except:
            continue

    # --- ACİL DURUM SENARYOSU (Asla Hata Vermez) ---
    print("Yapay zeka başarısız, Acil Durum Senaryosu devreye girdi.")
    fallback_script = (
        f"The story of {topic} is one of the most haunting mysteries of our time. "
        "It lies hidden beneath the surface, waiting to be discovered. "
        "Silence surrounds it, but if you listen closely, you can hear the echoes of the past. "
        "It is a tale of solitude, depth, and the unknown. "
        "A reminder that some things in this world are meant to remain unexplained."
    )
    # Konuya uygun anahtar kelimeler türet
    fallback_keywords = [topic, "ocean dark", "mystery", "fog"]
    return fallback_script, "cinematic", fallback_keywords, f"#shorts {topic}"

def download_music(mood, filename="bg.mp3"):
    if os.path.exists(filename): os.remove(filename)
    try:
        # Melankolik / Derin Müzik
        url = "https://cdn.pixabay.com/download/audio/2022/10/25/audio_5542f3603e.mp3"
        r = requests.get(url, timeout=15)
        if r.status_code == 200 and len(r.content) > 10000:
            with open(filename, "wb") as f: f.write(r.content)
            return True
    except: return False
    return False

def get_stock_videos(keywords, duration):
    headers = {"Authorization": PEXELS_API_KEY}
    # Görsel çeşitliliği
    search_terms = keywords + ["cinematic atmosphere", "dark nature"]
    paths, curr_dur, i = [], 0, 0
    
    for q in search_terms:
        if curr_dur >= duration + 5: break
        try:
            r = requests.get(f"https://api.pexels.com/videos/search?query={q}&per_page=4&orientation=portrait", headers=headers, timeout=10)
            data = r.json().get("videos", [])
            for v in data:
                if curr_dur >= duration + 5: break
                best_link = next((f["link"] for f in v["video_files"] if f["height"] >= 1080), None)
                if not best_link: best_link = v["video_files"][0]["link"]
                
                path = f"v{i}.mp4"
                with open(path, "wb") as f: f.write(requests.get(best_link).content)
                c = VideoFileClip(path)
                paths.append(path)
                curr_dur += c.duration
                c.close()
                i += 1
        except: pass
    
    if not paths: raise Exception("Görsel bulunamadı.")
    return paths

def create_subs(text, duration, size):
    W, H = size
    font_path = get_safe_font()
    try: font = ImageFont.truetype(font_path, int(W/12)) if font_path else ImageFont.load_default()
    except: font = ImageFont.load_default()
    
    words = text.split()
    chunks = []
    curr = []
    for w in words:
        curr.append(w)
        if len(curr) >= 2: 
            chunks.append(" ".join(curr))
            curr = []
    if curr: chunks.append(" ".join(curr))
    
    clips = []
    dur_per = duration / len(chunks)
    for chunk in chunks:
        img = Image.new('RGBA', (int(W), int(H)), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        lines = textwrap.wrap(chunk.upper(), width=20)
        y = H * 0.70 # Alt kısma yakın
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font)
            w_txt, h_txt = bbox[2]-bbox[0], bbox[3]-bbox[1]
            # Estetik yarı saydam bar
            draw.rectangle([(W-w_txt)/2 - 15, y - 10, (W+w_txt)/2 + 15, y + h_txt + 10], fill=(0,0,0,140))
            draw.text(((W-w_txt)/2, y), line, font=font, fill="#FFFFFF", stroke_width=1, stroke_fill="black")
            y += h_txt + 20
        clips.append(ImageClip(np.array(img)).set_duration(dur_per))
    return concatenate_videoclips(clips)

def build_final_video(topic, script, mood, keywords):
    temp = []
    try:
        generate_tts(script, "voice.mp3")
        temp.append("voice.mp3")
        audio = AudioFileClip("voice.mp3")
        
        has_music = download_music(mood, "bg.mp3")
        if has_music: temp.append("bg.mp3")
        
        v_paths = get_stock_videos(keywords, audio.duration)
        temp.extend(v_paths)
        
        clips = []
        for p in v_paths:
            c = VideoFileClip(p)
            c = c.resize(height=1080)
            if c.w % 2 != 0: c = c.resize(width=c.w + 1)
            
            TARGET_W = 608
            if c.w > TARGET_W:
                x_center = c.w / 2
                x1 = int(x_center - (TARGET_W / 2))
                c = c.crop(x1=x1, width=TARGET_W, height=1080)
            else:
                c = c.resize(width=TARGET_W, height=1080)
            c = c.resize(newsize=(TARGET_W, 1080))
            clips.append(c)

        current_dur = sum([c.duration for c in clips])
        while current_dur < audio.duration:
            clips.extend([c.copy() for c in clips])
            current_dur = sum([c.duration for c in clips])
            
        main = concatenate_videoclips(clips, method="compose")
        main = main.subclip(0, audio.duration)
        
        if has_music:
            try:
                # Müzik sesini arka planda kalacak şekilde kıstık
                bg = AudioFileClip("bg.mp3").volumex(0.15)
                bg = afx.audio_loop(bg, duration=main.duration)
                main = main.set_audio(CompositeAudioClip([audio, bg]))
            except: main = main.set_audio(audio)
        else: main = main.set_audio(audio)
            
        subs = create_subs(script, main.duration, main.size)
        final = CompositeVideoClip([main, subs])
        
        out = f"final_{int(time.time())}.mp4"
        final.write_videofile(out, codec="libx264", audio_codec="aac", fps=30, preset="medium", bitrate="5000k", ffmpeg_params=["-pix_fmt", "yuv420p"], threads=4)
        temp.append(out)
        
        for c in clips: c.close()
        audio.close()
        return out, temp
    except Exception as e:
        raise e

@bot.message_handler(commands=['video'])
def handle(m):
    try:
        if len(m.text.split()) < 2:
            bot.reply_to(m, "Konu girin: /video [Konu]")
            return
        topic = m.text.split(maxsplit=1)[1]
        msg = bot.reply_to(m, f"🎙️ '{topic}' için kayıt stüdyosuna giriliyor...\n(İngiliz Aksanı + Sinematik Mod)")
        
        script, mood, keywords, desc = get_script_and_metadata(topic)
        
        bot.edit_message_text(f"✅ Senaryo Hazır!\n🎬 Yönetmen Kurgusu Başladı...", m.chat.id, msg.message_id)
        
        path, files = build_final_video(topic, script, mood, keywords)
        
        with open(path, 'rb') as v:
            bot.send_video(m.chat.id, v, caption=desc)
        cleanup_files(files)
        bot.delete_message(m.chat.id, msg.message_id)
    except Exception as e:
        bot.reply_to(m, f"❌ Kritik Hata: {str(e)}")
        cleanup_files(locals().get('files', []))

print("Bot Başlatıldı (V24 - UNBREAKABLE)...")
bot.polling(non_stop=True)
