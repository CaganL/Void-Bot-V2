import os
import telebot
import requests
import random
import json
import time
import textwrap
import numpy as np
from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeVideoClip,
    concatenate_videoclips, CompositeAudioClip
)
from moviepy.audio.fx.all import volumex, audio_loop # audio_loop eklendi
import asyncio
import edge_tts

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")

def kill_webhook():
    if not TELEGRAM_TOKEN: return
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except: pass

kill_webhook()
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
W, H = 1080, 1920

# --- PİXABAY MÜZİK ---
def get_pixabay_music(query):
    try:
        # Daha fazla seçenek içinden rastgele müzik seçimi
        url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&media_type=music"
        r = requests.get(url, timeout=10).json()
        if r.get("hits"):
            music_url = random.choice(r["hits"])["preview"]
            path = "bg_music.mp3"
            with open(path, "wb") as f:
                f.write(requests.get(music_url, timeout=15).content)
            return path
    except: return None
    return None

# --- AI İÇERİK ---
def get_content(topic):
    models = ["gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
    prompt = (
        f"Create a viral horror/mystery script about '{topic}'. Under 90 words. "
        "Provide a 'music_keyword' for Pixabay. "
        "Output ONLY JSON: "
        "{'script': 'text', 'hook': 'HOOK', 'title': 'Title', 'hashtags': '#tags', 'music_keyword': 'dark', 'visual_keywords': ['tag1', 'tag2']}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                text = r.json()['candidates'][0]['content']['parts'][0]['text']
                return json.loads(text.replace("```json", "").replace("```", "").strip())
        except: continue
    return None

# --- MEDYA VE SES (VİDEO ÇEŞİTLİLİĞİ VE SES DÜZELTME) ---
async def generate_resources(content):
    script = content["script"]
    hook = content.get("hook", "")
    keywords = content["visual_keywords"]
    m_keyword = content.get("music_keyword", "mystery")
    
    # 🎙️ Seslendirme
    full_script = f"{hook}! {script}"
    smooth_script = full_script.replace(". ", ", ").replace("\n", " ")
    await edge_tts.Communicate(smooth_script, "en-US-AvaNeural", rate="+4%").save("voice.mp3")
    voice_audio = AudioFileClip("voice.mp3")
    
    # 🎵 Müzik Mikseri (Loop ve Ses Artışı)
    music_file = get_pixabay_music(m_keyword)
    if music_file:
        try:
            bg_music = AudioFileClip(music_file)
            # Müziği videonun sonuna kadar döngüye al ve sesini %45 yap
            bg_music = audio_loop(bg_music, duration=voice_audio.duration).fx(volumex, 0.45)
            final_audio = CompositeAudioClip([voice_audio, bg_music])
        except: final_audio = voice_audio
    else: final_audio = voice_audio
    
    # 🎥 Video Çeşitliliği (Rastgele Seçim)
    headers = {"Authorization": PEXELS_API_KEY}
    paths = []
    current_dur = 0
    for q in keywords:
        if current_dur >= voice_audio.duration: break
        try:
            # 15 sonuç isteyip içinden rastgele seçerek çeşitliliği sağlıyoruz
            url = f"https://api.pexels.com/videos/search?query={q}&per_page=15&orientation=portrait"
            data = requests.get(url, headers=headers, timeout=10).json()
            videos = data.get("videos", [])
            if videos:
                v = random.choice(videos) # Her seferinde farklı video seçer
                link = sorted(v.get("video_files", []), key=lambda x: x["height"], reverse=True)[0]["link"]
                path = f"clip_{len(paths)}.mp4"
                with open(path, "wb") as f:
                    f.write(requests.get(link, timeout=15).content)
                c = VideoFileClip(path)
                paths.append(path)
                current_dur += c.duration
                c.close()
        except: continue
        
    return paths, final_audio, music_file

def smart_resize(clip):
    target_ratio = W / H
    if (clip.w / clip.h) > target_ratio:
        clip = clip.resize(height=H).crop(x1=clip.w/2 - W/2, width=W, height=H)
    else:
        clip = clip.resize(width=W).crop(y1=clip.h/2 - H/2, width=W, height=H)
    return clip

# --- MONTAJ ---
def build_video(content):
    music_file = None
    try:
        paths, final_audio, music_file = asyncio.run(generate_resources(content))
        if not paths: return None
        clips = [smart_resize(VideoFileClip(p).without_audio()) for p in paths]
        main_clip = concatenate_videoclips(clips, method="compose").set_audio(final_audio)
        if main_clip.duration > final_audio.duration: main_clip = main_clip.subclip(0, final_audio.duration)
        
        out = "final.mp4"
        main_clip.write_videofile(out, fps=24, codec="libx264", preset="medium", bitrate="4500k", logger=None)
        
        final_audio.close()
        for c in clips: c.close()
        for p in paths: 
            if os.path.exists(p): os.remove(p)
        if music_file and os.path.exists(music_file): os.remove(music_file)
        return out
    except: return None

@bot.message_handler(commands=["video"])
def handle_video(message):
    try:
        topic = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "mystery"
        bot.reply_to(message, f"🎭 **{topic}** için benzersiz görüntüler ve güçlü seslerle hazırlanıyor...")
        content = get_content(topic)
        path = build_video(content)
        if path:
            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=f"🔥 {content['hook']}\n\n{content['script']}")
    except: pass

print("🤖 Bot Başlatıldı!")
bot.polling(non_stop=True)
