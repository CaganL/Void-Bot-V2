import os
import telebot
import requests
import random
import time
import asyncio
import edge_tts
import numpy as np
from moviepy.editor import (
    VideoFileClip, AudioFileClip, concatenate_videoclips, vfx, concatenate_audioclips, AudioClip
)

# BS4 Koruması (Mixkit için)
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

# Varsayılan Ses: Antoni (Ciddi, Tok Erkek Sesi)
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "ErXwobaYiN019PkySvjV") 

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
W, H = 720, 1280

# --- SABİT ETİKETLER ---
FIXED_HASHTAGS = "#horror #shorts #scary #creepy #mystery #fyp"

# --- YASAKLI KELİMELER ---
BANNED_TERMS = [
    "happy", "smile", "laugh", "business", "corporate", "office", "working", 
    "family", "couple", "romantic", "wedding", "party", "celebration", 
    "wellness", "spa", "massage", "yoga", "relax", "calm", "bright", 
    "sunny", "beach", "holiday", "vacation", "funny", "cute", "baby",
    "shopping", "sale", "store", "market", "daylight", "sun", "blue sky"
]

# --- GEMINI: SENARYO OLUŞTURMA ---
def get_content(topic):
    models = ["gemini-exp-1206", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    safety_settings = [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"}]

    base_prompt = (
        f"You are a VICTIM describing a FATAL physical trauma in a '{topic}'. "
        "Strictly follow this format using '|||' as separator:\n"
        "CLICKBAIT TITLE ||| PUNCHY HOOK (Sensory POV) ||| SEO DESCRIPTION ||| NARRATION SCRIPT (45-55 WORDS) ||| VISUAL_SCENES_LIST ||| MAIN_LOCATION (1 Word) ||| 3_SEARCH_VARIANTS ||| #tags\n\n"
        "RULES (PRO MODE):\n"
        "1. NO STORYTELLING. No 'ran away', no 'screamed'.\n"
        "2. ENDING: Immediate system failure (e.g. 'Spine severed').\n"
        "3. VISUALS: Suggest 'Cracking ice', 'Red ink' for impact scenes.\n"
        "4. STYLE: Cold, Clinical."
    )
    
    for current_model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json={"contents": [{"parts": [{"text": base_prompt}]}], "safetySettings": safety_settings}, timeout=20)
            if r.status_code == 200:
                parts = r.json()['candidates'][0]['content']['parts'][0]['text'].split("|||")
                if len(parts) >= 8:
                    return {
                        "title": parts[0].strip(),
                        "hook": parts[1].strip(),
                        "script": parts[3].strip(),
                        "visual_queries": parts[4].split(","),
                        "tags": parts[7].strip(),
                        "location": parts[5].strip().lower()
                    }
        except: continue
    return None

def is_safe_video(video_url, tags=[]):
    text_to_check = (video_url + " " + " ".join(tags)).lower()
    for b in BANNED_TERMS:
        if b in text_to_check: return False
    return True

# --- STOK VİDEO ARAMA (Optimize Edildi) ---
def search_mixkit(query):
    if not BS4_AVAILABLE: return None
    try:
        url = f"https://mixkit.co/free-stock-video/{query.split()[0]}/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        videos = soup.find_all('video')
        if videos: return random.choice(videos[:5]).get('src')
    except: pass
    return None

def search_pexels(query):
    headers = {"Authorization": PEXELS_API_KEY}
    try:
        url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation=portrait"
        r = requests.get(url, headers=headers, timeout=5).json()
        if r.get("videos"):
            for v in r["videos"]:
                if is_safe_video(v.get("url", ""), v.get("tags", [])):
                    return v["video_files"][0]["link"]
    except: pass
    return None

def smart_scene_search(query):
    # Önce Pexels, yoksa Mixkit
    link = search_pexels(query)
    if not link: link = search_mixkit(query) 
    return link

# --- SES MOTORU: ELEVENLABS (Yedek: Edge-TTS) ---
def generate_elevenlabs_audio(text, filename):
    if not ELEVENLABS_API_KEY: return False
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": ELEVENLABS_API_KEY}
    # Turbo v2.5 kullanıyoruz (Hızlı ve Ucuz)
    data = {"text": text, "model_id": "eleven_turbo_v2_5", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
    
    try:
        r = requests.post(url, json=data, headers=headers, timeout=30)
        if r.status_code == 200:
            with open(filename, 'wb') as f: f.write(r.content)
            print("✅ ElevenLabs Başarılı")
            return True
        else:
            print(f"❌ ElevenLabs Hatası: {r.status_code} - {r.text}")
            return False
    except: return False

# --- KAYNAK OLUŞTURMA ---
async def generate_resources(content):
    hook = content["hook"]
    script = content["script"]
    visual_queries = content["visual_queries"]
    
    # 1. Ses Üretimi
    use_elevenlabs = True
    # Hook için dene
    if not generate_elevenlabs_audio(hook, "hook.mp3"):
        comm = edge_tts.Communicate(hook, "en-US-ChristopherNeural", rate="-5%", pitch="-5Hz")
        await comm.save("hook.mp3")
        use_elevenlabs = False

    # Script için dene
    if use_elevenlabs:
        if not generate_elevenlabs_audio(script, "script.mp3"):
             comm = edge_tts.Communicate(script, "en-US-ChristopherNeural", rate="-5%", pitch="-5Hz")
             await comm.save("script.mp3")
    else:
        comm = edge_tts.Communicate(script, "en-US-ChristopherNeural", rate="-5%", pitch="-5Hz")
        await comm.save("script.mp3")

    try:
        h_audio = AudioFileClip("hook.mp3")
        s_audio = AudioFileClip("script.mp3")
        silence = AudioClip(lambda t: [0, 0], duration=0.6, fps=44100)
        final_audio = concatenate_audioclips([h_audio, silence, s_audio])
        final_audio.write_audiofile("voice.mp3")
        h_audio.close()
        s_audio.close()
    except: return None

    # 2. Video İndirme
    paths = []
    used = set()
    curr_dur = 0
    target = final_audio.duration * 1.5

    for q in visual_queries:
        if curr_dur >= target: break 
        link = smart_scene_search(q)
        if link and link not in used:
            try:
                path = f"clip_{len(paths)}.mp4"
                r = requests.get(link, timeout=10)
                if r.status_code == 200:
                    with open(path, "wb") as f: f.write(r.content)
                    if os.path.getsize(path) > 1000:
                        c = VideoFileClip(path)
                        if c.duration > 1.0:
                            paths.append(path)
                            used.add(link)
                            curr_dur += 3
                        c.close()
            except: pass
    
    if not paths: return None
    return paths, final_audio

# --- EFEKTLER (V112 ile Aynı - Eksiksiz) ---
def clinical_grade(image):
    img_f = image.astype(float)
    gray = np.mean(img_f, axis=2, keepdims=True)
    desaturated = img_f * 0.4 + gray * 0.6 
    tint_matrix = np.array([0.8, 1.1, 1.2]) 
    graded_img = desaturated * tint_matrix
    graded_img = (graded_img - 128) * 1.2 + 128
    return np.clip(graded_img, 0, 255).astype(np.uint8)

def xray_effect(clip):
    return clip.fx(vfx.invert_colors)

def apply_processing(clip, duration, is_impact=False):
    if clip.duration < duration:
        clip = vfx.loop(clip, duration=duration)
    else:
        start = random.uniform(0, clip.duration - duration)
        clip = clip.subclip(start, start + duration)
    
    if clip.w/clip.h > W/H:
        clip = clip.resize(height=H).crop(x1=clip.w/2-W/2, width=W, height=H)
    else:
        clip = clip.resize(width=W).crop(y1=clip.h/2-H/2, width=W, height=H)

    # Yavaş Zoom
    clip = clip.resize(lambda t: 1 + 0.04 * t).set_position(('center', 'center'))
    
    if is_impact: clip = xray_effect(clip)
    else: clip = clip.fl_image(clinical_grade)
    return clip

# --- MONTAJ ---
def build_video(content):
    try:
        res = asyncio.run(generate_resources(content))
        if not res: return None
        paths, audio = res
            
        clips = []
        for i, p in enumerate(paths):
            try:
                c = VideoFileClip(p).without_audio()
                dur = random.uniform(2.5, 3.5)
                # Son klibi X-RAY yap (V112 Özelliği)
                is_impact = (i >= len(paths) - 1)
                clips.append(apply_processing(c, dur, is_impact))
            except: continue

        while sum(c.duration for c in clips) < audio.duration:
             if clips: 
                new_c = clips[0].copy().fx(vfx.blackwhite).fx(vfx.speedx, 0.6)
                clips.append(new_c)
             else: break

        final = concatenate_videoclips(clips, method="compose").set_audio(audio)
        final = final.subclip(0, audio.duration)
        
        out = "final_output.mp4"
        # ÇÖKME ÖNLEYİCİ: threads=1 (Railway için kritik)
        final.write_videofile(out, fps=24, codec="libx264", preset="ultrafast", bitrate="3000k", audio_bitrate="128k", threads=1, logger=None)
        
        audio.close()
        for c in clips: c.close()
        for p in paths: 
            if os.path.exists(p): os.remove(p)
        return out
    except Exception as e:
        print(f"Hata: {e}")
        return None

# --- TELEGRAM BOT KOMUTLARI ---
@bot.message_handler(commands=["horror", "video"])
def handle(message):
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary story"
        
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\nElevenLabs Modu (V114)...\n")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ İçerik üretilemedi.", message.chat.id, msg.message_id)
            return

        bot.edit_message_text(f"🎬 **{content['title']}**\n🎙️ Ses: ElevenLabs\n📍 Mekan: {content['location'].upper()}\n⏳ Render...", message.chat.id, msg.message_id)

        path = build_video(content)
        
        if path and os.path.exists(path):
            # DETAYLI CAPTION GERİ GELDİ
            final_tags = f"{FIXED_HASHTAGS} {content['tags']}"
            caption_text = (
                f"🪝 **HOOK:**\n{content['hook']}\n\n"
                f"🎬 **Başlık:**\n{content['title']}\n\n"
                f"📝 **Hikaye:**\n{content['script']}\n\n"
                f"#️⃣ **Etiketler:**\n{final_tags}"
            )
            # Telegram sınırı koruması
            if len(caption_text) > 1000: caption_text = caption_text[:1000]

            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=caption_text, timeout=600)
        else:
            bot.edit_message_text("❌ Render hatası.", message.chat.id, msg.message_id)
            
    except Exception as e:
        bot.reply_to(message, f"Hata: {e}")

if __name__ == "__main__":
    print("Bot başlatılıyor...")
    bot.polling(non_stop=True)
