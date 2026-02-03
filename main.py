import os
import telebot
import requests
import random
import subprocess
import numpy as np
import textwrap
import time
import glob
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, afx

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BACKGROUND_MUSIC = "background.mp3"  # Eğer varsa kullanılır

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Pillow Sürüm Yaması
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

# --- YARDIMCI: DOSYA TEMİZLİK ---
def cleanup_files(file_list):
    """İşlem bitince geçici dosyaları siler."""
    for f in file_list:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception as e:
                print(f"Silinemedi: {f} - {e}")

# --- FONT İNDİRME ---
def download_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        try:
            r = requests.get(url, timeout=10)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except:
            pass
    return font_path

# --- TTS (SESLENDİRME) ---
def generate_tts(text, output="voice.mp3"):
    try:
        cmd = [
            "edge-tts",
            "--voice", "en-US-ChristopherNeural",
            "--text", text,
            "--write-media", output
        ]
        subprocess.run(cmd, check=True)
        return True
    except Exception as e:
        print(f"TTS Hatası: {e}")
        return False

# --- GEMINI 1.5 PRO SENARYO ---
def get_script(topic):
    # DÜZELTME: Model 1.5 Pro olarak güncellendi
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        f"Write a viral, engaging, and intense story about '{topic}' for a YouTube Short. "
        "The story MUST start with a shocking hook or a question to grab attention immediately. "
        "Use short, punchy sentences. "
        "Length: strictly between 110-130 words. No intro, no outro, no hashtags in the text. Simple English."
    )
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"Gemini Hatası: {e}")
    return f"This is a story about {topic}. It is very mysterious and interesting. Watch to find out more."

# --- VİDEO İNDİRME (DİNAMİK) ---
def get_multiple_videos(topic, total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    
    # DÜZELTME: Konuya göre dinamik arama terimleri
    queries = [topic, f"{topic} aesthetic", f"{topic} cinematic", f"{topic} dark", f"{topic} intense"]
    
    # Konu özelinde eklemeler
    if any(x in topic.lower() for x in ['horror', 'scary', 'ghost', 'korku']):
        queries += ["dark room", "shadow", "creepy corridor"]
    elif any(x in topic.lower() for x in ['money', 'rich', 'success']):
        queries += ["luxury", "money", "city skyline night"]
        
    paths = []
    current_dur = 0
    i = 0
    random.shuffle(queries) # Çeşitlilik için karıştır
    
    try:
        # Arama döngüsü
        for q in queries:
            if current_dur >= total_duration:
                break
                
            search_url = f"https://api.pexels.com/videos/search?query={q}&per_page=5&orientation=portrait"
            r = requests.get(search_url, headers=headers, timeout=15)
            videos_data = r.json().get("videos", [])
            
            if not videos_data:
                continue
                
            # En uygun videoyu seç
            v = random.choice(videos_data)
            link = max(v["video_files"], key=lambda x: x["height"])["link"]
            
            path = f"part_{i}.mp4"
            i += 1
            
            # İndir
            with open(path, "wb") as f:
                f.write(requests.get(link, timeout=20).content)
            
            # Süre kontrolü
            clip = VideoFileClip(path)
            paths.append(path)
            current_dur += clip.duration
            clip.close()
            
        return paths if paths else None
    except Exception as e:
        print(f"Video İndirme Hatası: {e}")
        return None

# --- ALTYAZI ---
def split_for_subtitles(text):
    words = text.split()
    chunks = []
    current = []
    for w in words:
        current.append(w)
        if len(current) >= 4: # Her ekranda ortalama 4 kelime
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks

def create_subtitles(text, total_duration, video_size):
    W, H = video_size
    font_path = download_font()
    fontsize = int(W / 10) # Font boyutu ayarlandı
    
    try: font = ImageFont.truetype(font_path, fontsize)
    except: font = ImageFont.load_default()
        
    chunks = split_for_subtitles(text)
    duration_per_chunk = total_duration / len(chunks)
    clips = []
    
    for chunk in chunks:
        img = Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        wrapper = textwrap.TextWrapper(width=16)
        caption_wrapped = '\n'.join(wrapper.wrap(text=chunk.upper()))
        
        bbox = draw.textbbox((0, 0), caption_wrapped, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        
        # DÜZELTME: Altyazı konumu yukarı çekildi (0.75 -> 0.65)
        # Böylece YouTube arayüzünün altında kalmaz
        center_y = H * 0.65
        
        # Arka plan kutusu (Okunurluk için)
        box_padding = 15
        box_x1 = (W - tw) / 2 - box_padding
        box_y1 = center_y - box_padding
        box_x2 = (W + tw) / 2 + box_padding
        box_y2 = center_y + th + box_padding
        draw.rectangle([box_x1, box_y1, box_x2, box_y2], fill=(0, 0, 0, 140))
        
        draw.text(
            ((W - tw) / 2, center_y),
            caption_wrapped,
            font=font,
            fill="#FFD700", # Sarı renk (Shorts standardı)
            align="center",
            stroke_width=4,
            stroke_fill="black"
        )
        clips.append(ImageClip(np.array(img)).set_duration(duration_per_chunk))
        
    return concatenate_videoclips(clips)

# --- MONTAJ MOTORU ---
def build_video(topic, script, mode="final"):
    temp_files = [] # Silinecek dosyalar listesi
    try:
        # 1. Seslendirme
        if not generate_tts(script, "voice.mp3"):
            return "Seslendirme hatası.", []
        temp_files.append("voice.mp3")
        audio = AudioFileClip("voice.mp3")
        
        # 2. Videoları Bul (Konuya göre)
        paths = get_multiple_videos(topic, audio.duration)
        if not paths:
            return "İlgili video bulunamadı.", temp_files
        temp_files.extend(paths)
        
        video_clips = []
        for p in paths:
            c = VideoFileClip(p)
            
            # --- Boyut Güvenliği (Çift Sayı) ---
            new_h = 1080
            new_w = int(new_h * (c.w / c.h))
            new_w += new_w % 2 # Tek sayı ise +1 ekle
            c = c.resize(height=new_h, width=new_w)
            
            # --- 9:16 Kırpma ---
            target_w = int(new_h * (9 / 16))
            target_w += target_w % 2
            
            if c.w > target_w:
                x1 = int((c.w - target_w) / 2)
                c = c.crop(x1=x1, width=target_w, height=new_h)
            
            # FFMPEG Garantisi
            if c.w % 2 != 0: c = c.resize(width=c.w + 1)
            if c.h % 2 != 0: c = c.resize(height=c.h + 1)
                
            video_clips.append(c)
            
        main_video = concatenate_videoclips(video_clips, method="compose")
        
        # Ses Süresine Eşitle
        if main_video.duration > audio.duration:
             main_video = main_video.subclip(0, audio.duration)
        else:
             main_video = main_video.loop(duration=audio.duration)
        
        # Arka Plan Müziği (Varsa)
        if os.path.exists(BACKGROUND_MUSIC):
            music = AudioFileClip(BACKGROUND_MUSIC).subclip(0, main_video.duration).volumex(0.15) # Ses kısıldı
            main_video = main_video.set_audio(audio.audio_fadeout(0.5).fx(afx.audio_loop, duration=main_video.duration).volumex(1.0).fx(afx.audio_mix, music))
        else:
            main_video = main_video.set_audio(audio)
            
        # Altyazılar
        subs = create_subtitles(script, main_video.duration, main_video.size)
        final_result = CompositeVideoClip([main_video, subs])
        
        # Render Ayarları
        output_filename = f"final_{int(time.time())}.mp4"
        fps = 30 if mode == "final" else 24
        preset = "medium" if mode == "final" else "ultrafast"
        
        final_result.write_videofile(
            output_filename,
            codec="libx264",
            audio_codec="aac",
            fps=fps,
            preset=preset,
            ffmpeg_params=["-pix_fmt", "yuv420p"],
            threads=4
        )
        
        # Kaynakları serbest bırak
        for c in video_clips: c.close()
        audio.close()
        
        temp_files.append(output_filename) # Final videoyu da listeye ekle (gönderdikten sonra silmek için)
        return output_filename, temp_files

    except Exception as e:
        return f"Montaj Hatası: {str(e)}", temp_files

# --- AÇIKLAMA OLUŞTURUCU ---
def generate_description(script, topic):
    # Gemini 1.5 Pro'ya açıklama yazdırılabilir veya basit mantık kullanılabilir
    hashtags = f"#{topic.replace(' ', '')} #shorts #viral #fyp #storytime"
    if "horror" in topic.lower(): hashtags += " #scary #horror"
    elif "motivation" in topic.lower(): hashtags += " #motivation #success"
    
    return f"🎬 {topic.title()} Story\n\nWait for the end! 😱\n\n{hashtags}\n\nSubscribe for more! 👇"

# --- TELEGRAM HANDLER ---
@bot.message_handler(commands=['video'])
def handle_video(message):
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        bot.reply_to(message, "Lütfen bir konu yazın. Örnek: /video Space Mystery")
        return
        
    topic = args[1]
    mode = "final" # Varsayılan mod
    
    msg = bot.reply_to(message, f"🚀 **Gemini 1.5 Pro** çalışıyor: '{topic}' için senaryo yazılıyor...")
    
    # 1. Senaryo
    script = get_script(topic)
    bot.edit_message_text(f"📝 Senaryo hazır. Görseller '{topic}' bağlamında aranıyor ve montajlanıyor...", chat_id=message.chat.id, message_id=msg.message_id)
    
    # 2. Video Üretimi
    # build_video artık topic parametresini de alıyor!
    video_path, created_files = build_video(topic, script, mode=mode)
    
    if video_path.endswith(".mp4"):
        # Thumbnail oluştur
        thumb_path = "thumb.jpg"
        try:
            clip = VideoFileClip(video_path)
            clip.save_frame(thumb_path, t=1)
            clip.close()
            created_files.append(thumb_path)
        except: thumb_path = None

        description = generate_description(script, topic)
        
        with open(video_path, 'rb') as v:
            if thumb_path:
                with open(thumb_path, 'rb') as t:
                    bot.send_video(message.chat.id, v, caption=description, thumb=t)
            else:
                bot.send_video(message.chat.id, v, caption=description)
        
        bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
        
        # 3. Temizlik
        print("Dosyalar temizleniyor...")
        cleanup_files(created_files)
        
    else:
        bot.reply_to(message, f"❌ Hata oluştu: {video_path}")
        cleanup_files(created_files)

# --- BAŞLAT ---
print("Bot Başlatıldı (Pro Mode)...")
bot.polling(non_stop=True)

