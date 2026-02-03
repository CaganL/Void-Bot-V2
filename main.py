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

# Pillow Yama
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = getattr(Image, 'Resampling', Image).LANCZOS

def cleanup_files(file_list):
    for f in file_list:
        if os.path.exists(f):
            try: os.remove(f)
            except: pass

# --- GÜVENLİ FONT İNDİRİCİ ---
def get_safe_font():
    font_path = "Oswald-Bold.ttf"
    
    # Dosya varsa ama bozuksa (boyutu çok küçükse) sil
    if os.path.exists(font_path) and os.path.getsize(font_path) < 1000:
        os.remove(font_path)

    if not os.path.exists(font_path):
        try:
            # Alternatif güvenli linkler
            urls = [
                "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf",
                "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf" # Yedek font
            ]
            
            for url in urls:
                try:
                    r = requests.get(url, timeout=10)
                    if r.status_code == 200:
                        with open(font_path, "wb") as f: f.write(r.content)
                        break
                except: continue
        except Exception as e: print(f"Font İndirme Hatası: {e}")
    
    # Hala dosya yoksa veya bozuksa None dön (Default font kullanılsın)
    if os.path.exists(font_path) and os.path.getsize(font_path) > 1000:
        return font_path
    return None

def generate_tts(text, output="voice.mp3"):
    try:
        subprocess.run(["edge-tts", "--voice", "en-US-ChristopherNeural", "--text", text, "--write-media", output], check=True)
        return True
    except FileNotFoundError:
        raise Exception("Sunucuda 'edge-tts' yüklü değil! requirements.txt dosyanı kontrol et.")
    except Exception as e:
        raise Exception(f"Seslendirme Hatası: {str(e)}")

def get_script_and_metadata(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        f"Act as a professional YouTube Shorts scriptwriter. Create a video script about '{topic}'.\n"
        "Rules:\n"
        "1. Script length: 110-130 words strictly.\n"
        "2. Start with a shocking hook.\n"
        "3. Output Format JSON:\n"
        "{ \"script\": \"...\", \"mood\": \"horror OR motivation OR happy\", \"description\": \"viral description with hashtags\" }"
    )
    
    for attempt in range(3):
        try:
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
            if r.status_code == 200:
                raw = r.json()['candidates'][0]['content']['parts'][0]['text']
                raw = raw.replace("```json", "").replace("```", "").strip()
                data = json.loads(raw)
                if len(data.get("script", "").split()) < 30: raise ValueError("Script too short")
                return data["script"], data.get("mood", "cinematic"), data.get("description", f"#shorts {topic}")
        except: time.sleep(1)
    
    fallback = f"Did you know about {topic}? It is fascinating. Subscribe for more facts."
    return fallback, "cinematic", f"#shorts {topic}"

def download_music(mood, filename="bg.mp3"):
    library = {
        "horror": "https://cdn.pixabay.com/download/audio/2022/03/09/audio_c8c8a73467.mp3",
        "motivation": "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3",
        "cinematic": "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3"
    }
    try:
        url = library.get("cinematic")
        for k in library: 
            if k in mood.lower(): url = library[k]
        with open(filename, "wb") as f: f.write(requests.get(url).content)
        return True
    except: return False

def get_stock_videos(topic, duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = [topic, "abstract background", "cinematic", "nature", "city"]
    paths, curr_dur, i = [], 0, 0
    
    for q in queries:
        if curr_dur >= duration: break
        try:
            r = requests.get(f"https://api.pexels.com/videos/search?query={q}&per_page=3&orientation=portrait", headers=headers, timeout=10)
            data = r.json().get("videos", [])
            
            for v in data:
                if curr_dur >= duration: break
                link = max(v["video_files"], key=lambda x: x["height"])["link"]
                path = f"v{i}.mp4"
                with open(path, "wb") as f: f.write(requests.get(link).content)
                c = VideoFileClip(path)
                paths.append(path)
                curr_dur += c.duration
                c.close()
                i += 1
        except Exception as e: print(f"Video İndirme Hatası ({q}): {e}")
        
    if not paths: raise Exception("Hiçbir video indirilemedi! Pexels API Key kontrol et veya konu değiştir.")
    return paths

# --- HATA DÜZELTİLDİ: create_subs ---
def create_subs(text, duration, size):
    W, H = size
    
    # FONT YÜKLEME (GÜVENLİ)
    font_path = get_safe_font()
    try:
        if font_path:
            font = ImageFont.truetype(font_path, int(W/10))
        else:
            raise Exception("Font yok")
    except:
        # Eğer font bozuksa varsayılan fontu yükle (Çökmemesi için)
        print("Uyarı: Özel font yüklenemedi, varsayılan font kullanılıyor.")
        font = ImageFont.load_default()

    words = text.split()
    chunks = []
    curr = []
    for w in words:
        curr.append(w)
        if len(curr) >= 3:
            chunks.append(" ".join(curr))
            curr = []
    if curr: chunks.append(" ".join(curr))
    
    clips = []
    dur_per = duration / len(chunks)
    for chunk in chunks:
        img = Image.new('RGBA', (int(W), int(H)), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        lines = textwrap.wrap(chunk.upper(), width=15)
        y = H * 0.60
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            
            # Siyah kutu
            draw.rectangle([(W-w)/2 - 10, y - 10, (W+w)/2 + 10, y + h + 10], fill=(0,0,0,180))
            
            # Yazı rengi (Varsayılan fontta renk desteklenmeyebilir ama deniyoruz)
            draw.text(((W-w)/2, y), line, font=font, fill="#FFD700", stroke_width=0 if font_path is None else 3, stroke_fill="black")
            y += h + 10
        clips.append(ImageClip(np.array(img)).set_duration(dur_per))
    return concatenate_videoclips(clips)

def build_final_video(topic, script, mood):
    temp = []
    try:
        generate_tts(script, "voice.mp3")
        temp.append("voice.mp3")
        audio = AudioFileClip("voice.mp3")
        
        has_music = download_music(mood, "bg.mp3")
        if has_music: temp.append("bg.mp3")
        
        v_paths = get_stock_videos(topic, audio.duration)
        temp.extend(v_paths)
        
        clips = []
        for p in v_paths:
            c = VideoFileClip(p)
            nh = 1080
            nw = int(nh * c.w / c.h)
            if nw % 2 != 0: nw += 1
            c = c.resize(height=nh, width=nw)
            tw = 608
            if c.w > tw: c = c.crop(x1=(c.w-tw)/2, width=tw, height=nh)
            clips.append(c)
            
        main = concatenate_videoclips(clips, method="compose")
        if main.duration > audio.duration: main = main.subclip(0, audio.duration)
        else: main = main.loop(duration=audio.duration)
        
        if has_music:
            bg = AudioFileClip("bg.mp3").volumex(0.15)
            if bg.duration < main.duration: bg = afx.audio_loop(bg, duration=main.duration)
            else: bg = bg.subclip(0, main.duration)
            final_audio = CompositeAudioClip([audio, bg])
            main = main.set_audio(final_audio)
        else: main = main.set_audio(audio)
            
        subs = create_subs(script, main.duration, main.size)
        final = CompositeVideoClip([main, subs])
        
        out = f"final_{int(time.time())}.mp4"
        final.write_videofile(out, codec="libx264", audio_codec="aac", fps=24, preset="ultrafast", threads=4)
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
        
        msg = bot.reply_to(m, f"🕵️ Hata Ayıklama Modu: '{topic}' işleniyor...")
        
        script, mood, desc = get_script_and_metadata(topic)
        path, files = build_final_video(topic, script, mood)
        
        with open(path, 'rb') as v:
            bot.send_video(m.chat.id, v, caption=f"✅ BAŞARILI!\n\n{desc}")
        
        cleanup_files(files)
        bot.delete_message(m.chat.id, msg.message_id)
        
    except Exception as e:
        error_msg = f"❌ KRİTİK HATA OLUŞTU:\n\n{str(e)}\n\n{traceback.format_exc()}"
        if len(error_msg) > 4000: error_msg = error_msg[-4000:]
        bot.reply_to(m, error_msg)
        cleanup_files(locals().get('files', []))

print("Bot Başlatıldı (Safe Mode)...")
bot.polling(non_stop=True)
