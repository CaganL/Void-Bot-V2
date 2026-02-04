import os
import telebot
import requests
import random
import subprocess
import numpy as np
import textwrap
import time
import json
import traceback
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

def generate_tts(text, output="voice.mp3"):
    try:
        subprocess.run(["edge-tts", "--voice", "en-US-ChristopherNeural", "--text", text, "--write-media", output], check=True)
        return True
    except: return False

# --- SENARYO MOTORU (FLASH ÖNCELİKLİ) ---
def get_script_and_metadata(topic):
    # SIRALAMA GÜNCELLENDİ: 2.5 Flash Başta!
    models = [
        "models/gemini-2.5-flash",     # 1. HIZLI VE YENİ (Favori)
        "models/gemini-2.0-flash",     # 2. Alternatif Hızlı
        "models/gemini-1.5-flash",     # 3. GARANTİ YEDEK
    ]
    
    prompt = (
        f"You are a viral content creator. Write a script about '{topic}'.\n"
        "RULES:\n"
        "1. HOOK: Start with a shocking question/statement.\n"
        "2. TONE: Storytelling, deep, and engaging.\n"
        "3. VISUALS: Provide 3 SPECIFIC visual keywords (e.g. 'storm clouds', 'crying eye').\n"
        "4. FORMAT: JSON {{ \"script\": \"...\", \"keywords\": [\"...\", \"...\"] }}"
    )
    
    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GEMINI_API_KEY}"
        print(f"Deneniyor: {model_name}...")
        
        try:
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
            if r.status_code == 200:
                raw = r.json()['candidates'][0]['content']['parts'][0]['text']
                try:
                    start = raw.find('{')
                    end = raw.rfind('}') + 1
                    if start != -1 and end != -1:
                        data = json.loads(raw[start:end])
                        if len(data.get("script", "").split()) > 30:
                             return data.get("script"), "cinematic", data.get("keywords", [topic]), f"#shorts {topic}"
                except:
                    clean = raw.replace("```json", "").replace("```", "").strip()
                    if len(clean.split()) > 30:
                        return clean, "cinematic", [topic], f"#shorts {topic}"
        except Exception as e:
            print(f"{model_name} hata verdi, sıradakine geçiliyor...")
            time.sleep(1)
            continue

    # Hepsi çökerse (Zor ihtimal)
    fallback = (f"Did you know the incredible story of {topic}? Most people have no idea. "
                "It involves details that are absolutely mind-blowing. "
                "Experts have been studying this for years. "
                "Stay tuned to learn more about this fascinating topic.")
    return fallback, "cinematic", [topic], f"#shorts {topic}"

def download_music(mood, filename="bg.mp3"):
    if os.path.exists(filename): os.remove(filename)
    try:
        r = requests.get("https://cdn.pixabay.com/download/audio/2022/03/09/audio_c8c8a73467.mp3", timeout=15)
        if r.status_code == 200 and len(r.content) > 50000:
            with open(filename, "wb") as f: f.write(r.content)
            return True
    except: return False
    return False

def get_stock_videos(keywords, duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = keywords if isinstance(keywords, list) else [keywords]
    paths, curr_dur, i = [], 0, 0
    
    for q in queries:
        if curr_dur >= duration + 10: break
        try:
            r = requests.get(f"https://api.pexels.com/videos/search?query={q}&per_page=5&orientation=portrait", headers=headers, timeout=10)
            data = r.json().get("videos", [])
            for v in data:
                if curr_dur >= duration + 10: break
                best_link = next((f["link"] for f in v["video_files"] if f["height"] >= 1080), None)
                if not best_link:
                     best_link = next((f["link"] for f in v["video_files"] if f["height"] > 700), v["video_files"][0]["link"])
                
                path = f"v{i}.mp4"
                with open(path, "wb") as f: f.write(requests.get(best_link).content)
                c = VideoFileClip(path)
                paths.append(path)
                curr_dur += c.duration
                c.close()
                i += 1
        except: pass
    if not paths: raise Exception("Görsel video bulunamadı.")
    return paths

def create_subs(text, duration, size):
    W, H = size
    font_path = get_safe_font()
    try: font = ImageFont.truetype(font_path, int(W/10)) if font_path else ImageFont.load_default()
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
        y = H * 0.65 
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font)
            w_txt, h_txt = bbox[2]-bbox[0], bbox[3]-bbox[1]
            x_pos = (W-w_txt)/2
            stroke_w = 6
            draw.text((x_pos, y), line, font=font, fill="#FFD700", stroke_width=stroke_w, stroke_fill="black")
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
                bg = AudioFileClip("bg.mp3").volumex(0.12)
                bg = afx.audio_loop(bg, duration=main.duration)
                main = main.set_audio(CompositeAudioClip([audio, bg]))
            except: main = main.set_audio(audio)
        else:
            main = main.set_audio(audio)
            
        subs = create_subs(script, main.duration, main.size)
        final = CompositeVideoClip([main, subs])
        
        out = f"final_{int(time.time())}.mp4"
        final.write_videofile(out, codec="libx264", audio_codec="aac", fps=30, preset="slow", bitrate="6000k", ffmpeg_params=["-pix_fmt", "yuv420p"], threads=4)
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
        
        msg = bot.reply_to(m, f"⚡ '{topic}' için **GEMINI 2.5 FLASH** ile hızlandırılmış üretim başladı...")
        
        script, mood, keywords, desc = get_script_and_metadata(topic)
        
        keywords_str = ", ".join(keywords) if isinstance(keywords, list) else keywords
        bot.edit_message_text(f"✅ Senaryo 2.5 Flash ile Hazır!\n🖼️ Görseller: {keywords_str}\n⏳ Film işleniyor (6000k Bitrate)...", m.chat.id, msg.message_id)
        
        path, files = build_final_video(topic, script, mood, keywords)
        
        with open(path, 'rb') as v:
            bot.send_video(m.chat.id, v, caption=desc)
        cleanup_files(files)
        bot.delete_message(m.chat.id, msg.message_id)
    except Exception as e:
        error_msg = str(e)
        if "Google" in error_msg or "429" in error_msg:
             error_msg = "⚠️ Modeller meşgul. Lütfen 30 saniye sonra tekrar deneyin."
        bot.reply_to(m, f"❌ İşlem Durduruldu: {error_msg}")
        cleanup_files(locals().get('files', []))

print("Bot Başlatıldı (V21 - FLASH TURBO)...")
bot.polling(non_stop=True)
