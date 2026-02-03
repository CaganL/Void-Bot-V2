import os
import telebot
import requests
import random
import asyncio
import edge_tts
import numpy as np
import textwrap
from PIL import Image, ImageDraw, ImageFont 
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

# --- AYARLAR ---
TELEGRAM_TOKEN = "8395962603:AAFmuGIsQ2DiUD8nV7ysUjkGbsr1dmGlqKo"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

def download_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        try:
            r = requests.get(url)
            with open(font_path, "wb") as f: f.write(r.content)
        except: pass
    return font_path

# --- 1. SENARYO MOTORU ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (f"Write a viral and terrifying horror story about '{topic}' for a YouTube Short. "
              "Length must be around 115-125 words. No intro or outro. Simple English only.")
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=12)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except: pass
    return "I looked into the mirror and saw my own reflection. But it was smiling even though I was crying. Then, it slowly reached out from the glass and grabbed my throat."

# --- 2. ÇOKLU VİDEO İNDİRİCİ ---
def get_multiple_videos(query, total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    search_url = f"https://api.pexels.com/videos/search?query={query}&per_page=12&orientation=portrait"
    try:
        r = requests.get(search_url, headers=headers)
        videos_data = r.json().get("videos", [])
        if not videos_data: return None
        paths = []
        current_dur = 0
        for i, v in enumerate(videos_data[:5]):
            if current_dur >= total_duration: break
            link = max(v["video_files"], key=lambda x: x["height"])["link"]
            path = f"part_{i}.mp4"
            with open(path, "wb") as f: f.write(requests.get(link).content)
            clip = VideoFileClip(path)
            paths.append(path)
            current_dur += clip.duration
            clip.close()
        return paths
    except: return None

# --- 3. ALTYAZI SİSTEMİ ---
def create_subtitles(text, total_duration, video_size):
    W, H = video_size
    font_path = download_font()
    fontsize = int(W / 12) 
    try: font = ImageFont.truetype(font_path, fontsize)
    except: font = ImageFont.load_default()
    sentences = text.replace(".", ".|").replace("?", "?|").replace("!", "!|").split("|")
    chunks = [s.strip() for s in sentences if s.strip()]
    duration_per_chunk = total_duration / len(chunks)
    clips = []
    for chunk in chunks:
        img = Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        wrapper = textwrap.TextWrapper(width=int(W/22))
        caption_wrapped = '\n'.join(wrapper.wrap(text=chunk))
        bbox = draw.textbbox((0, 0), caption_wrapped, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text(((W-tw)/2, H*0.7), caption_wrapped, font=font, fill="#FFD700", align="center", stroke_width=4, stroke_fill="black")
        clips.append(ImageClip(np.array(img)).set_duration(duration_per_chunk))
    return concatenate_videoclips(clips)

# --- 4. MONTAJ MOTORU (YAMA EKLENDİ) ---
def build_video(topic, script):
    try:
        asyncio.run(edge_tts.Communicate(script, "en-US-ChristopherNeural").save("voice.mp3"))
        audio = AudioFileClip("voice.mp3")
        paths = get_multiple_videos(topic, audio.duration)
        if not paths: return "Görüntü bulunamadı."
        video_clips = []
        for p in paths:
            c = VideoFileClip(p)
            # KRİTİK YAMA: Boyutların her zaman çift sayı olmasını sağlıyoruz
            new_h = 1080
            new_w = int((new_h * (c.w / c.h)) // 2) * 2 # En yakın çift sayıya yuvarla
            c = c.resize(height=new_h, width=new_w)
            
            # 9:16 Kırpma (W her zaman çift olacak)
            target_w = int((new_h * (9/16)) // 2) * 2
            if c.w > target_w:
                c = c.crop(x1=(c.w/2 - target_w/2), width=target_w, height=new_h)
            video_clips.append(c)
            
        main_video = concatenate_videoclips(video_clips, method="compose")
        if main_video.duration < audio.duration:
            main_video = main_video.loop(duration=audio.duration)
        else:
            main_video = main_video.subclip(0, audio.duration)
        main_video = main_video.set_audio(audio)
        subs = create_subtitles(script, main_video.duration, main_video.size)
        final_result = CompositeVideoClip([main_video, subs])
        
        # Render
        final_result.write_videofile(
            "final_video.mp4", 
            codec="libx264", 
            audio_codec="aac", 
            fps=24, 
            preset='ultrafast', 
            ffmpeg_params=["-pix_fmt", "yuv420p"],
            threads=4
        )
        for c in video_clips: c.close()
        audio.close()
        return "final_video.mp4"
    except Exception as e: return f"Hata: {str(e)}"

@bot.message_handler(commands=['video'])
def handle_video(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Lütfen bir konu yaz.")
        return
    topic = args[1]
    bot.reply_to(message, f"🎥 '{topic}' işleniyor...")
    script = get_script(topic)
    video_path = build_video(topic, script)
    if "final_video" in video_path:
        with open(video_path, 'rb') as v:
            bot.send_video(message.chat.id, v, caption=f"🎬 **Konu:** {topic}")
    else:
        bot.reply_to(message, video_path)

bot.polling()
