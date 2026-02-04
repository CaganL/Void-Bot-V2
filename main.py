import os
import telebot
import requests
import random
import subprocess
import numpy as np
import textwrap
import time
import json
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

# --- SES MOTORU (BELGESEL TONU) ---
def generate_tts(text, output="voice.mp3"):
    try:
        # Ryan (İngiliz) - Yavaş ve Tok Ses
        subprocess.run(["edge-tts", "--voice", "en-GB-RyanNeural", "--rate=-10%", "--pitch=-2Hz", "--text", text, "--write-media", output], check=True)
        return True
    except: 
        try:
            subprocess.run(["edge-tts", "--voice", "en-US-ChristopherNeural", "--text", text, "--write-media", output], check=True)
            return True
        except: return False

# --- ZEKİ SENARYO MOTORU (MULTI-MODEL) ---
def get_script_and_metadata(topic):
    # Senin listendeki modelleri sırayla deneyeceğiz
    models = [
        "models/gemini-1.5-flash",   # En kararlı olan
        "models/gemini-2.0-flash",   # Yeni nesil
        "models/gemini-1.5-pro"      # Yedek güç
    ]
    
    # Prompt: "Gerçekleri anlat" (Fact-Based)
    prompt = (
        f"Act as a documentary filmmaker. Write a script about '{topic}'.\n"
        "RULES:\n"
        "1. NO FLUFF. Provide 3 specific, surprising facts (like names, dates, numbers).\n"
        "2. Narrative style: Start with the most shocking detail.\n"
        "3. Length: 100-110 words.\n"
        "4. END with: KEYWORDS: visual1, visual2, visual3\n"
    )
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_API_KEY}"
        print(f"Model deneniyor: {model}")
        try:
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=25)
            if r.status_code == 200:
                text = r.json()['candidates'][0]['content']['parts'][0]['text']
                
                # Yedek metin mi diye kontrol et (Eğer çok kısaysa reddet)
                if len(text.split()) < 30: continue
                
                parts = text.split("KEYWORDS:")
                script = parts[0].strip().replace("*", "").replace("#", "")
                
                if len(parts) > 1:
                    keywords = [k.strip() for k in parts[1].split(",")]
                else:
                    keywords = [topic, "cinematic", "documentary"]
                
                # Sinematik eklemeler
                final_keywords = keywords[:3] + ["cinematic 4k", "slow motion nature"]
                
                return script, "cinematic", final_keywords, f"#shorts {topic}"
        except Exception as e:
            print(f"{model} hatası: {e}")
            time.sleep(1)
            continue

    # Eğer hepsi patlarsa (İmkansız ama) -> Kullanıcıya dürüst olalım
    raise Exception("Yapay zeka modelleri şu an cevap veremiyor. Lütfen 2 dakika sonra tekrar dene.")

def download_music(mood, filename="bg.mp3"):
    if os.path.exists(filename): os.remove(filename)
    try:
        # Daha dramatik, derin bir müzik
        url = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3"
        r = requests.get(url, timeout=15)
        if r.status_code == 200 and len(r.content) > 10000:
            with open(filename, "wb") as f: f.write(r.content)
            return True
    except: return False
    return False

def get_stock_videos(keywords, duration):
    headers = {"Authorization": PEXELS_API_KEY}
    paths, curr_dur, i = [], 0, 0
    
    for q in keywords:
        if curr_dur >= duration + 5: break
        try:
            r = requests.get(f"https://api.pexels.com/videos/search?query={q}&per_page=5&orientation=portrait", headers=headers, timeout=10)
            data = r.json().get("videos", [])
            for v in data:
                if curr_dur >= duration + 5: break
                # En yüksek kaliteyi bul
                best_link = next((f["link"] for f in v["video_files"] if f["height"] >= 1080), None)
                if not best_link: best_link = v["video_files"][0]["link"]
                
                path = f"v{i}.mp4"
                with open(path, "wb") as f: f.write(requests.get(best_link).content)
                c = VideoFileClip(path)
                if c.duration > 3: # Çok kısa videoları alma
                    paths.append(path)
                    curr_dur += c.duration
                c.close()
                i += 1
        except: pass
    
    if not paths: raise Exception("Stok video bulunamadı.")
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
        y = H * 0.70
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font)
            w_txt, h_txt = bbox[2]-bbox[0], bbox[3]-bbox[1]
            draw.rectangle([(W-w_txt)/2 - 15, y - 10, (W+w_txt)/2 + 15, y + h_txt + 10], fill=(0,0,0,140))
            draw.text(((W-w_txt)/2, y), line, font=font, fill="#FFFFFF", stroke_width=1, stroke_fill="black")
            y += h_txt + 20
        clips.append(ImageClip(np.array(img)).set_duration(dur_per))
    return concatenate_videoclips(clips)

# --- ZOOM EFEKTİ (Hareket Katmak İçin) ---
def zoom_in_effect(clip, zoom_ratio=0.04):
    def effect(get_frame, t):
        img = Image.fromarray(get_frame(t))
        base_size = img.size
        new_size = [
            int(base_size[0] * (1 + (zoom_ratio * t))),
            int(base_size[1] * (1 + (zoom_ratio * t)))
        ]
        img = img.resize(new_size, Image.LANCZOS)
        x = (new_size[0] - base_size[0]) // 2
        y = (new_size[1] - base_size[1]) // 2
        img = img.crop([x, y, x + base_size[0], y + base_size[1]])
        return np.array(img)
    return clip.fl(effect)

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
            
            # ZOOM EFEKTİ UYGULA
            c = zoom_in_effect(c)
            
            clips.append(c)

        current_dur = sum([c.duration for c in clips])
        while current_dur < audio.duration:
            clips.extend([c.copy() for c in clips])
            current_dur = sum([c.duration for c in clips])
            
        main = concatenate_videoclips(clips, method="compose")
        main = main.subclip(0, audio.duration)
        
        if has_music:
            try:
                bg = AudioFileClip("bg.mp3").volumex(0.15)
                bg = afx.audio_loop(bg, duration=main.duration)
                main = main.set_audio(CompositeAudioClip([audio, bg]))
            except: main = main.set_audio(audio)
        else: main = main.set_audio(audio)
            
        subs = create_subs(script, main.duration, main.size)
        final = CompositeVideoClip([main, subs])
        
        out = f"final_{int(time.time())}.mp4"
        final.write_videofile(out, codec="libx264", audio_codec="aac", fps=30, preset="slow", bitrate="5000k", ffmpeg_params=["-pix_fmt", "yuv420p"], threads=4)
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
        msg = bot.reply_to(m, f"🎬 '{topic}' için gerçek bir belgesel hazırlanıyor...")
        
        script, mood, keywords, desc = get_script_and_metadata(topic)
        
        keywords_str = ", ".join(keywords[:3]) if isinstance(keywords, list) else keywords
        bot.edit_message_text(f"✅ Senaryo Onaylandı!\n(Yedek metin değil, orijinal hikaye)\n🖼️ Görseller: {keywords_str}\n⏳ Sinematik Render (Zoom Effect)...", m.chat.id, msg.message_id)
        
        path, files = build_final_video(topic, script, mood, keywords)
        
        with open(path, 'rb') as v:
            bot.send_video(m.chat.id, v, caption=desc)
        cleanup_files(files)
        bot.delete_message(m.chat.id, msg.message_id)
    except Exception as e:
        bot.reply_to(m, f"❌ Hata: {str(e)}")
        cleanup_files(locals().get('files', []))

print("Bot Başlatıldı (V26 - REAL STORY + ZOOM)...")
bot.polling(non_stop=True)
