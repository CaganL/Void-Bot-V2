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

def generate_tts(text, output="voice.mp3"):
    try:
        # Ryan (UK) - Belgesel Sesi
        subprocess.run(["edge-tts", "--voice", "en-GB-RyanNeural", "--rate=-10%", "--pitch=-2Hz", "--text", text, "--write-media", output], check=True)
        return True
    except: return False

# --- V30 AKILLI SENARYO MOTORU (KOTA DOSTU) ---
def get_script_and_metadata(topic):
    # Senin listendeki modellerin TAM isimleri
    models = [
        "models/gemini-2.0-flash", 
        "models/gemini-2.0-flash-lite-preview-02-05", 
        "models/gemini-1.5-pro",
        "models/gemini-pro"
    ]
    
    prompt = (
        f"Act as a documentary filmmaker. Write a script about '{topic}'.\n"
        "RULES:\n"
        "1. Write 3 specific, surprising facts woven into a story.\n"
        "2. NO INTRO. Start directly with the first fact.\n"
        "3. Tone: Serious and viral.\n"
        "4. Length: 100 words.\n"
        "5. Output format: [Script text] KEYWORDS: [3 visual terms]"
    )
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_API_KEY}"
        print(f"Model deneniyor: {model}")
        
        try:
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            
            # KOTA DOLDUYSA (429 Hatası)
            if r.status_code == 429:
                print("Kota dolu! 10 saniye bekleniyor...")
                time.sleep(10) # Bekle ve aynı modelle tekrar dene veya sonrakine geç
                continue
            
            if r.status_code == 200:
                text = r.json()['candidates'][0]['content']['parts'][0]['text']
                
                if "KEYWORDS:" in text:
                    parts = text.split("KEYWORDS:")
                    script = parts[0].strip().replace("*", "").replace("#", "")
                    keywords = [k.strip() for k in parts[1].split(",")]
                else:
                    script = text.strip()
                    keywords = [topic, "cinematic", "documentary"]

                return script, keywords[:3]
            else:
                print(f"{model} Hata Kodu: {r.status_code}")
                continue

        except Exception as e:
            print(f"{model} Bağlantı Hatası: {e}")
            time.sleep(2)
            continue

    # Hiçbiri çalışmazsa
    raise Exception("Tüm modeller denendi ancak Google API yanıt vermiyor (Muhtemelen kota dolu). Lütfen 5 dakika sonra tekrar dene.")

def get_stock_videos(keywords, duration):
    headers = {"Authorization": PEXELS_API_KEY}
    paths, curr_dur, i = [], 0, 0
    search_queries = keywords + ["cinematic atmosphere", "dark nature", "abstract background"]
    
    for q in search_queries:
        if curr_dur >= duration + 5: break
        try:
            r = requests.get(f"https://api.pexels.com/videos/search?query={q}&per_page=3&orientation=portrait", headers=headers, timeout=10)
            data = r.json().get("videos", [])
            for v in data:
                if curr_dur >= duration + 5: break
                link = next((f["link"] for f in v["video_files"] if f["height"] >= 1080), v["video_files"][0]["link"])
                path = f"v{i}.mp4"
                with open(path, "wb") as f: f.write(requests.get(link).content)
                c = VideoFileClip(path)
                if c.duration > 3:
                    paths.append(path)
                    curr_dur += c.duration
                c.close()
                i += 1
        except: pass
    
    if not paths: raise Exception("Pexels'ten video bulunamadı.")
    return paths

# --- SINEMATİK ZOOM ---
def zoom_in_effect(clip, zoom_ratio=0.04):
    def effect(get_frame, t):
        img = Image.fromarray(get_frame(t))
        base_size = img.size
        new_size = [int(base_size[0] * (1 + (zoom_ratio * t))), int(base_size[1] * (1 + (zoom_ratio * t)))]
        img = img.resize(new_size, Image.LANCZOS)
        x, y = (new_size[0] - base_size[0]) // 2, (new_size[1] - base_size[1]) // 2
        return np.array(img.crop([x, y, x + base_size[0], y + base_size[1]]))
    return clip.fl(effect)

def build_final_video(topic, script, keywords):
    temp = []
    try:
        generate_tts(script, "voice.mp3")
        temp.append("voice.mp3")
        audio = AudioFileClip("voice.mp3")
        
        # Müzik
        r = requests.get("https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3", timeout=15)
        if r.status_code == 200:
            with open("bg.mp3", "wb") as f: f.write(r.content)
            temp.append("bg.mp3")
        
        v_paths = get_stock_videos(keywords, audio.duration)
        temp.extend(v_paths)
        
        clips = []
        for p in v_paths:
            c = VideoFileClip(p).resize(height=1080)
            if c.w % 2 != 0: c = c.resize(width=c.w + 1)
            c = c.crop(x1=(c.w - 608) // 2, width=608, height=1080).resize(newsize=(608, 1080))
            clips.append(zoom_in_effect(c))

        main = concatenate_videoclips(clips, method="compose").subclip(0, audio.duration)
        
        if os.path.exists("bg.mp3"):
            bg = AudioFileClip("bg.mp3").volumex(0.12)
            bg = afx.audio_loop(bg, duration=main.duration)
            main = main.set_audio(CompositeAudioClip([audio, bg]))
        else: main = main.set_audio(audio)
            
        # Altyazı
        font_path = get_safe_font()
        words = script.split()
        subs_clips = []
        dur_per_word = main.duration / len(words)
        
        for i in range(0, len(words), 2):
            chunk = " ".join(words[i:i+2]).upper()
            img = Image.new('RGBA', (608, 1080), (0,0,0,0))
            draw = ImageDraw.Draw(img)
            f = ImageFont.truetype(font_path, 55) if font_path else ImageFont.load_default()
            w_txt, h_txt = draw.textbbox((0,0), chunk, font=f)[2:]
            draw.rectangle([(608-w_txt)/2-15, 760, (608+w_txt)/2+15, 760+h_txt+15], fill=(0,0,0,180))
            draw.text(((608-w_txt)/2, 760), chunk, font=f, fill="white")
            subs_clips.append(ImageClip(np.array(img)).set_duration(dur_per_word * 2))
        
        subs = concatenate_videoclips(subs_clips)
        final = CompositeVideoClip([main, subs])
        
        out = f"final_{int(time.time())}.mp4"
        final.write_videofile(out, codec="libx264", audio_codec="aac", fps=30, preset="slow", bitrate="6000k", threads=4)
        temp.append(out)
        return out, temp
    except Exception as e: raise e

@bot.message_handler(commands=['video'])
def handle(m):
    try:
        topic = m.text.split(maxsplit=1)[1]
        msg = bot.reply_to(m, f"🎬 '{topic}' için senaryo (V30 - Akıllı Bekleme Modu) hazırlanıyor...\n(Hata alırsam tekrar deneyeceğim, lütfen bekleyin)")
        script, keywords = get_script_and_metadata(topic)
        path, files = build_final_video(topic, script, keywords)
        with open(path, 'rb') as v: bot.send_video(m.chat.id, v)
        cleanup_files(files)
        bot.delete_message(m.chat.id, msg.message_id)
    except Exception as e:
        bot.reply_to(m, f"❌ Hata: {str(e)}")
        cleanup_files(locals().get('files', []))

print("Bot Başlatıldı (V30 - ANTI-QUOTA)...")
bot.polling(non_stop=True)
