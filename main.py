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

# --- AYARLAR (Railway Variables'dan Otomatik Çeker) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY") 
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Pillow Sürüm Yaması (Hata Önleyici)
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = getattr(Image, 'Resampling', Image).LANCZOS

# --- TEMİZLİK ---
def cleanup_files(file_list):
    for f in file_list:
        if os.path.exists(f):
            try: os.remove(f)
            except: pass

# --- FONT ---
def download_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        try:
            with open(font_path, "wb") as f: f.write(requests.get(url, timeout=10).content)
        except: pass
    return font_path

# --- TTS ---
def generate_tts(text, output="voice.mp3"):
    try:
        subprocess.run(["edge-tts", "--voice", "en-US-ChristopherNeural", "--text", text, "--write-media", output], check=True)
        return True
    except: return False

# --- GEMINI ZEKASI (RETRY MEKANİZMALI) ---
def get_script_and_metadata(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={GEMINI_API_KEY}"
    
    # Prompt: Hem hikaye, hem mood, hem de viral açıklama istiyoruz
    prompt = (
        f"Act as a professional YouTube Shorts scriptwriter. Create a video script about '{topic}'.\n"
        "Rules:\n"
        "1. Script length: 110-130 words strictly.\n"
        "2. Start with a shocking hook.\n"
        "3. Output Format JSON:\n"
        "{ \"script\": \"...\", \"mood\": \"horror OR motivation OR happy\", \"description\": \"viral description with hashtags\" }"
    )
    
    # 3 Kez Deneme Hakkı (Retry Logic)
    for attempt in range(3):
        try:
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
            if r.status_code == 200:
                # Temizleme (Markdown ```json ... ``` kısımlarını siler)
                raw = r.json()['candidates'][0]['content']['parts'][0]['text']
                raw = raw.replace("```json", "").replace("```", "").strip()
                data = json.loads(raw)
                
                # Kontrol: Script çok kısaysa hata say ve tekrar dene
                if len(data.get("script", "").split()) < 50:
                    raise ValueError("Script too short")
                    
                return data["script"], data.get("mood", "cinematic"), data.get("description", f"#shorts {topic}")
        except Exception as e:
            print(f"Deneme {attempt+1} başarısız: {e}")
            time.sleep(1)
    
    # Hepsi başarısız olursa uzun bir yedek metin (3 sn video olmasın diye)
    fallback_script = (
        f"Did you know about {topic}? It is one of the most fascinating topics in the world. "
        "Many people don't realize the hidden secrets behind it. "
        "Scientists and experts have been studying this for years. "
        "If you look closely, you will see details that blow your mind. "
        "Stay tuned for more facts like this and subscribe for daily updates."
    )
    return fallback_script, "cinematic", f"Amazing facts about {topic} #shorts"

# --- MÜZİK ---
def download_music(mood, filename="bg.mp3"):
    # Manuel Liste (Güvenli Linkler)
    library = {
        "horror": "https://cdn.pixabay.com/download/audio/2022/03/09/audio_c8c8a73467.mp3",
        "motivation": "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3",
        "happy": "https://cdn.pixabay.com/download/audio/2022/01/21/audio_31743c58bd.mp3",
        "cinematic": "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3"
    }
    # Mood'a en yakınını bul
    url = library.get("cinematic")
    for key in library:
        if key in mood.lower():
            url = library[key]
            break
            
    try:
        with open(filename, "wb") as f: f.write(requests.get(url).content)
        return True
    except: return False

# --- VİDEO İNDİRME ---
def get_stock_videos(topic, duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = [topic, f"{topic} dark", f"{topic} aesthetic", "abstract background"]
    random.shuffle(queries)
    paths, curr_dur, i = [], 0, 0
    
    for q in queries:
        if curr_dur >= duration: break
        try:
            r = requests.get(f"https://api.pexels.com/videos/search?query={q}&per_page=4&orientation=portrait", headers=headers, timeout=10)
            data = r.json().get("videos", [])
            if not data: continue
            
            v = random.choice(data)
            link = max(v["video_files"], key=lambda x: x["height"])["link"]
            path = f"v{i}.mp4"
            with open(path, "wb") as f: f.write(requests.get(link).content)
            
            c = VideoFileClip(path)
            paths.append(path)
            curr_dur += c.duration
            c.close()
            i += 1
        except: pass
    return paths

# --- ALTYAZI ---
def create_subs(text, duration, size):
    W, H = size
    font = ImageFont.truetype(download_font(), int(W/10))
    
    words = text.split()
    chunks = []
    curr = []
    for w in words:
        curr.append(w)
        if len(curr) >= 3: # 3 kelimede bir böl
            chunks.append(" ".join(curr))
            curr = []
    if curr: chunks.append(" ".join(curr))
    
    clips = []
    dur_per = duration / len(chunks)
    
    for chunk in chunks:
        img = Image.new('RGBA', (int(W), int(H)), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        
        # Text Wrap
        lines = textwrap.wrap(chunk.upper(), width=15)
        y = H * 0.60 # Konum (Ortanın altı)
        
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            
            # Siyah Arkaplan
            draw.rectangle([(W-w)/2 - 10, y - 10, (W+w)/2 + 10, y + h + 10], fill=(0,0,0,180))
            # Sarı Yazı
            draw.text(((W-w)/2, y), line, font=font, fill="#FFD700", stroke_width=3, stroke_fill="black")
            y += h + 10
            
        clips.append(ImageClip(np.array(img)).set_duration(dur_per))
    
    return concatenate_videoclips(clips)

# --- MONTAJ ---
def build_final_video(topic, script, mood):
    temp = []
    try:
        # 1. Seslendirme
        generate_tts(script, "voice.mp3")
        temp.append("voice.mp3")
        audio = AudioFileClip("voice.mp3")
        
        # 2. Müzik
        has_music = download_music(mood, "bg.mp3")
        if has_music: temp.append("bg.mp3")
        
        # 3. Görsel
        v_paths = get_stock_videos(topic, audio.duration)
        if not v_paths: return None, temp
        temp.extend(v_paths)
        
        clips = []
        for p in v_paths:
            c = VideoFileClip(p)
            # Boyut Garantisi (Çift Sayı - Hata Önleyici)
            nh = 1080
            nw = int(nh * c.w / c.h)
            if nw % 2 != 0: nw += 1
            c = c.resize(height=nh, width=nw)
            
            # Crop 9:16
            tw = 608
            if c.w > tw:
                c = c.crop(x1=(c.w-tw)/2, width=tw, height=nh)
            
            clips.append(c)
            
        main = concatenate_videoclips(clips, method="compose")
        
        # Süre Ayarı
        if main.duration > audio.duration: main = main.subclip(0, audio.duration)
        else: main = main.loop(duration=audio.duration)
        
        # Ses Birleştirme
        if has_music:
            bg = AudioFileClip("bg.mp3").volumex(0.15)
            if bg.duration < main.duration: bg = afx.audio_loop(bg, duration=main.duration)
            else: bg = bg.subclip(0, main.duration)
            final_audio = CompositeAudioClip([audio, bg])
            main = main.set_audio(final_audio)
        else:
            main = main.set_audio(audio)
            
        # Altyazı
        subs = create_subs(script, main.duration, main.size)
        final = CompositeVideoClip([main, subs])
        
        out = f"final_{int(time.time())}.mp4"
        final.write_videofile(out, codec="libx264", audio_codec="aac", fps=24, preset="medium", threads=4)
        temp.append(out)
        
        # Kapat
        for c in clips: c.close()
        audio.close()
        
        return out, temp
    except Exception as e:
        print(e)
        return None, temp

@bot.message_handler(commands=['video'])
def handle(m):
    try:
        # Eğer sadece /video yazıldıysa uyarı ver
        if len(m.text.split()) < 2:
            bot.reply_to(m, "Lütfen bir konu yazın: /video [Konu]")
            return
        topic = m.text.split(maxsplit=1)[1]
    except:
        bot.reply_to(m, "Konu yazın: /video Konu")
        return
        
    msg = bot.reply_to(m, f"🎬 '{topic}' hazırlanıyor... (Bu 1-2 dk sürebilir)")
    
    # 1. Gemini'den Veri Al (3 Deneme Hakkı Var)
    script, mood, desc = get_script_and_metadata(topic)
    
    # 2. Video Yap
    path, files = build_final_video(topic, script, mood)
    
    if path:
        with open(path, 'rb') as v:
            # Viral açıklamayı videonun altına ekle
            bot.send_video(m.chat.id, v, caption=desc)
        cleanup_files(files)
        bot.delete_message(m.chat.id, msg.message_id)
    else:
        bot.reply_to(m, "Video oluşturulamadı.")
        cleanup_files(files)

print("Bot Başlatıldı (Railway Modu)...")
bot.polling(non_stop=True)
