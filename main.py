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

# --- GEMINI ZEKASI (GÖRSEL ARAMA TERİMLERİ EKLENDİ) ---
def get_script_and_metadata(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    # Prompt güncellendi: Artık 'visual_keywords' de istiyoruz
    prompt = (
        f"Write a YouTube Short script about '{topic}'.\n"
        "1. Length: 100-120 words. Start with a hook.\n"
        "2. VISUALS: Provide 3-4 english search terms for stock videos based on the script content.\n"
        "3. Output JSON: {{ \"script\": \"...\", \"mood\": \"horror/happy/motivation\", \"keywords\": [\"term1\", \"term2\", \"term3\"], \"description\": \"...\" }}"
    )
    
    for attempt in range(3):
        try:
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
            if r.status_code == 200:
                raw = r.json()['candidates'][0]['content']['parts'][0]['text']
                try:
                    start = raw.find('{')
                    end = raw.rfind('}') + 1
                    if start != -1 and end != -1:
                        data = json.loads(raw[start:end])
                        # Eğer keywords listesi gelmezse konuyu kullan
                        keywords = data.get("keywords", [topic, "cinematic", "4k"])
                        return data.get("script", raw), data.get("mood", "cinematic"), keywords, f"#shorts {topic}"
                except: pass
                
                # JSON başarısızsa manuel fallback
                if len(raw.split()) > 20:
                    return raw.replace("*", "").strip(), "cinematic", [topic, "abstract"], f"#shorts {topic}"
        except Exception as e:
            time.sleep(1)
            
    return f"Here are facts about {topic}.", "cinematic", [topic, "nature"], f"#shorts {topic}"

def download_music(mood, filename="bg.mp3"):
    library = {
        "horror": "https://cdn.pixabay.com/download/audio/2022/03/09/audio_c8c8a73467.mp3",
        "motivation": "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3",
        "cinematic": "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3",
        "happy": "https://cdn.pixabay.com/download/audio/2022/01/21/audio_31743c58bd.mp3"
    }
    try:
        url = library.get("cinematic")
        for k in library: 
            if k in mood.lower(): url = library[k]
        with open(filename, "wb") as f: f.write(requests.get(url).content)
        return True
    except: return False

# --- VİDEO ARAMA (ARTIK GÖRSEL TERİMLERİ KULLANIYOR) ---
def get_stock_videos(keywords, duration):
    headers = {"Authorization": PEXELS_API_KEY}
    # Gemini'den gelen özel kelimeleri kullan
    queries = keywords if isinstance(keywords, list) else [keywords]
    
    paths, curr_dur, i = [], 0, 0
    
    # Her anahtar kelime için arama yap
    for q in queries:
        if curr_dur >= duration: break
        try:
            r = requests.get(f"https://api.pexels.com/videos/search?query={q}&per_page=2&orientation=portrait", headers=headers, timeout=10)
            data = r.json().get("videos", [])
            for v in data:
                if curr_dur >= duration: break
                
                # Kalite Filtresi: 1080p'ye en yakın olanı seç
                best_link = None
                min_diff = float('inf')
                for f in v["video_files"]:
                    if f["height"] > 600:
                        diff = abs(f["height"] - 1080)
                        if diff < min_diff:
                            min_diff = diff
                            best_link = f["link"]
                if not best_link: best_link = max(v["video_files"], key=lambda x: x["height"])["link"]
                
                path = f"v{i}.mp4"
                with open(path, "wb") as f: f.write(requests.get(best_link).content)
                c = VideoFileClip(path)
                paths.append(path)
                curr_dur += c.duration
                c.close()
                i += 1
        except: pass
    
    if not paths: raise Exception("Video bulunamadı. Pexels Key kontrol et.")
    return paths

# --- ALTYAZI İYİLEŞTİRMESİ ---
def create_subs(text, duration, size):
    W, H = size
    font_path = get_safe_font()
    try:
        font = ImageFont.truetype(font_path, int(W/12)) if font_path else ImageFont.load_default()
    except: font = ImageFont.load_default()

    words = text.split()
    chunks = []
    curr = []
    # Kelime sayısını azalttık (Daha az sıkışık olsun diye)
    for w in words:
        curr.append(w)
        if len(curr) >= 2: # Her satırda max 2-3 kelime
            chunks.append(" ".join(curr))
            curr = []
    if curr: chunks.append(" ".join(curr))
    
    clips = []
    dur_per = duration / len(chunks)
    
    for chunk in chunks:
        img = Image.new('RGBA', (int(W), int(H)), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        
        # Metni sar (Wrap) - Genişliği artırdık
        lines = textwrap.wrap(chunk.upper(), width=20)
        
        # Konum: Ekranın biraz daha altına
        y = H * 0.65
        
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            
            # Siyah Kutu (Daha geniş padding)
            pad = 15
            draw.rectangle([(W-w)/2 - pad, y - pad, (W+w)/2 + pad, y + h + pad], fill=(0,0,0,170))
            
            # Yazı
            draw.text(((W-w)/2, y), line, font=font, fill="#FFD700", stroke_width=2, stroke_fill="black")
            y += h + 25 # Satır aralığını açtık
            
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
        
        # Görsel terimleri kullan
        v_paths = get_stock_videos(keywords, audio.duration)
        temp.extend(v_paths)
        
        clips = []
        for p in v_paths:
            c = VideoFileClip(p)
            
            # Zorunlu 608x1080 Boyutlandırma
            TARGET_W, TARGET_H = 608, 1080
            c = c.resize(height=TARGET_H)
            if c.w > TARGET_W:
                c = c.crop(x1=(c.w - TARGET_W) // 2, width=TARGET_W, height=TARGET_H)
            else:
                c = c.resize(width=TARGET_W, height=TARGET_H)
            c = c.resize(newsize=(TARGET_W, TARGET_H))
            
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
        
        # --- KALİTE AYARLARI GÜNCELLENDİ ---
        # Bitrate: 4500k (Daha net görüntü)
        # Preset: medium (Daha iyi sıkıştırma, biraz daha yavaş ama kaliteli)
        final.write_videofile(out, codec="libx264", audio_codec="aac", fps=24, preset="medium", bitrate="4500k", ffmpeg_params=["-pix_fmt", "yuv420p"], threads=4)
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
        msg = bot.reply_to(m, f"🎬 '{topic}' analiz ediliyor...")
        
        # Metadata'dan keywords'ü de alıyoruz artık
        script, mood, keywords, desc = get_script_and_metadata(topic)
        
        # Kullanıcıya görsel terimleri göster (Eğlenceli olsun)
        keywords_str = ", ".join(keywords) if isinstance(keywords, list) else keywords
        bot.edit_message_text(f"🎥 Görseller aranıyor: {keywords_str}\nMood: {mood}", m.chat.id, msg.message_id)
        
        path, files = build_final_video(topic, script, mood, keywords)
        
        with open(path, 'rb') as v:
            bot.send_video(m.chat.id, v, caption=desc)
        cleanup_files(files)
        bot.delete_message(m.chat.id, msg.message_id)
        
    except Exception as e:
        bot.reply_to(m, f"❌ Hata: {str(e)}")
        cleanup_files(locals().get('files', []))

print("Bot Başlatıldı (High Quality & Smart Search)...")
bot.polling(non_stop=True)
