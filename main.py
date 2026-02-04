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

# --- YENİ SES MOTORU (BELGESEL TONU) ---
def generate_tts(text, output="voice.mp3"):
    try:
        # SES AYARLARI:
        # en-GB-RyanNeural: İngiliz aksanı (Daha ciddi ve kaliteli duyulur)
        # --rate=-10%: Konuşma hızı %10 yavaşlatıldı (Tane tane anlatım)
        # --pitch=-2Hz: Ses tonu biraz kalınlaştırıldı (Tok ses)
        command = [
            "edge-tts",
            "--voice", "en-GB-RyanNeural",
            "--rate=-10%",
            "--pitch=-2Hz",
            "--text", text,
            "--write-media", output
        ]
        subprocess.run(command, check=True)
        return True
    except Exception as e:
        print(f"TTS Hatası: {e}")
        return False

# --- HİKAYE MOTORU ---
def get_script_and_metadata(topic):
    # En yetenekli modeller
    models = ["models/gemini-2.5-flash", "models/gemini-2.0-flash", "models/gemini-1.5-flash"]
    
    prompt = (
        f"Write a short, dramatic storytelling script about '{topic}' for a TikTok video.\n"
        "RULES:\n"
        "1. DO NOT use intro phrases like 'Did you know'. Start directly with the action or mystery.\n"
        "2. Make it emotional and engaging. Use short sentences.\n"
        "3. Length: Around 100 words.\n"
        "4. At the very end, add a line starting with 'KEYWORDS:' followed by 3 visual search terms.\n"
        "Example output:\n"
        "He walked into the room and froze. The silence was deafening... [Story continues]...\n"
        "KEYWORDS: shadow, fear, dark room"
    )
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=25)
            if r.status_code == 200:
                text = r.json()['candidates'][0]['content']['parts'][0]['text']
                parts = text.split("KEYWORDS:")
                script = parts[0].strip().replace("*", "").replace("#", "")
                
                if len(parts) > 1:
                    keywords = [k.strip() for k in parts[1].split(",")]
                else:
                    keywords = [topic]
                
                # Sinematik hava için ek terimler
                keywords.extend(["cinematic", "4k", "moody", "slow motion"])
                
                if len(script.split()) > 20:
                    return script, "cinematic", keywords, f"#shorts {topic}"
        except:
            time.sleep(1)
            continue

    raise Exception("Hikaye oluşturulamadı. Lütfen başka bir konu deneyin.")

def download_music(mood, filename="bg.mp3"):
    if os.path.exists(filename): os.remove(filename)
    try:
        url = "https://cdn.pixabay.com/download/audio/2022/03/09/audio_c8c8a73467.mp3"
        r = requests.get(url, timeout=15)
        if r.status_code == 200 and len(r.content) > 50000:
            with open(filename, "wb") as f: f.write(r.content)
            return True
    except: return False
    return False

def get_stock_videos(keywords, duration):
    headers = {"Authorization": PEXELS_API_KEY}
    search_terms = keywords[:2] + ["abstract dark", "cinematic nature"]
    paths, curr_dur, i = [], 0, 0
    
    for q in search_terms:
        if curr_dur >= duration + 10: break
        try:
            r = requests.get(f"https://api.pexels.com/videos/search?query={q}&per_page=5&orientation=portrait", headers=headers, timeout=10)
            data = r.json().get("videos", [])
            for v in data:
                if curr_dur >= duration + 10: break
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
    try: font = ImageFont.truetype(font_path, int(W/11)) if font_path else ImageFont.load_default()
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
        lines = textwrap.wrap(chunk.upper(), width=16)
        y = H * 0.60
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font)
            w_txt, h_txt = bbox[2]-bbox[0], bbox[3]-bbox[1]
            # Yarı saydam siyah arka plan (Okunabilirlik için en iyisi)
            draw.rectangle([(W-w_txt)/2 - 10, y - 5, (W+w_txt)/2 + 10, y + h_txt + 5], fill=(0,0,0,160))
            draw.text(((W-w_txt)/2, y), line, font=font, fill="#FFFFFF", stroke_width=2, stroke_fill="black")
            y += h_txt + 15
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
                bg = AudioFileClip("bg.mp3").volumex(0.20)
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
        msg = bot.reply_to(m, f"🎙️ '{topic}' hazırlanıyor...\n(Yeni Ses: Ryan - UK Accent)")
        
        script, mood, keywords, desc = get_script_and_metadata(topic)
        
        bot.edit_message_text(f"✅ Hikaye Hazır!\n🖼️ Görseller: {', '.join(keywords[:3])}\n⏳ Film işleniyor...", m.chat.id, msg.message_id)
        
        path, files = build_final_video(topic, script, mood, keywords)
        
        with open(path, 'rb') as v:
            bot.send_video(m.chat.id, v, caption=desc)
        cleanup_files(files)
        bot.delete_message(m.chat.id, msg.message_id)
    except Exception as e:
        bot.reply_to(m, f"❌ Hata: {str(e)}")
        cleanup_files(locals().get('files', []))

print("Bot Başlatıldı (V23 - NEW VOICE)...")
bot.polling(non_stop=True)
