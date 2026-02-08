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

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
W, H = 720, 1280

# --- SABİT ETİKETLER ---
FIXED_HASHTAGS = "#horror #shorts #scary #creepy #mystery #fyp"

# --- YASAKLI KELİMELER LİSTESİ (FİLTRE) ---
# Eğer video linkinde veya etiketlerinde bunlar varsa, o videoyu ASLA kullanma.
BANNED_TERMS = [
    "happy", "smile", "laugh", "business", "corporate", "office", "working", 
    "family", "couple", "romantic", "wedding", "party", "celebration", 
    "wellness", "spa", "massage", "yoga", "relax", "calm", "bright", 
    "sunny", "beach", "holiday", "vacation", "funny", "cute", "baby"
]

# --- YEDEK KORKU LİNKLERİ (HARDCODED FALLBACK) ---
# Pexels/Pixabay saçmalarsa kullanılacak garanti korku videoları
FALLBACK_HORROR_VIDEOS = [
    "https://videos.pexels.com/video-files/5435032/5435032-hd_720_1280_25fps.mp4", # Glitch
    "https://videos.pexels.com/video-files/7655848/7655848-hd_720_1280_30fps.mp4", # Shadow
    "https://videos.pexels.com/video-files/6954203/6954203-hd_720_1280_25fps.mp4", # Fog
    "https://videos.pexels.com/video-files/8056976/8056976-hd_720_1280_25fps.mp4", # Dark Water
    "https://videos.pexels.com/video-files/4990242/4990242-hd_720_1280_30fps.mp4"  # Scary Forest
]

# --- TEMİZLİK ---
def clean_start():
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except: pass

# --- AI İÇERİK (V42: VİRGÜLLÜ SIKIŞTIRILMIŞ MOD) ---
def get_content(topic):
    models = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-flash-latest", "gemini-2.5-flash"]
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    # PROMPT: "ATMOSPHERE FIRST"
    prompt = (
        f"You are a viral horror shorts director. Write a script about '{topic}'. "
        "Strictly follow this format using '|||' as separator:\n"
        "CLICKBAIT TITLE (Max 4 words) ||| PUNCHY HOOK (Max 6 words) ||| SEO DESCRIPTION ||| NARRATION SCRIPT (60-70 words) ||| VISUAL_QUERIES (15 TERMS) ||| #tag1 #tag2 #tag3\n\n"
        "CRITICAL RULES:\n"
        "1. VISUAL QUERIES: Give me 15 terms. FOCUS ON LIGHTING AND TEXTURE, NOT JUST OBJECTS.\n"
        "   - BAD: 'hand', 'door', 'face'\n"
        "   - GOOD: 'silhouette in doorway', 'rusty metal texture', 'flickering light bulb', 'shadow hand on wall'\n"
        "2. LENGTH: 60-70 words.\n"
        "3. HOOK: Scary and spoken first."
    )
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": safety_settings
    }

    print(f"🤖 Gemini'ye soruluyor: {topic}...")

    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json=payload, timeout=20)
            
            if r.status_code == 429:
                time.sleep(2)
                continue

            if r.status_code == 200:
                response_json = r.json()
                if 'candidates' in response_json and response_json['candidates']:
                    raw_text = response_json['candidates'][0]['content']['parts'][0]['text']
                    parts = raw_text.split("|||")
                    
                    if len(parts) >= 6:
                        raw_tags = parts[5].strip().replace(",", " ").split()
                        valid_tags = [t for t in raw_tags if t.startswith("#")]
                        visual_queries = [v.strip() for v in parts[4].split(",")]
                        
                        while len(visual_queries) < 15:
                            visual_queries.append("scary dark cinematic atmosphere")

                        data = {
                            "title": parts[0].strip(),
                            "hook": parts[1].strip(),
                            "description": parts[2].strip(),
                            "script": parts[3].strip(),
                            "visual_queries": visual_queries,
                            "tags": " ".join(valid_tags)
                        }
                        print(f"✅ İçerik alındı ({model})")
                        return data
        except: continue

    return None

# --- AKILLI FİLTRELEME FONKSİYONU ---
def is_safe_video(video_url, tags=[]):
    """
    Video URL'si veya etiketleri 'yasaklı kelimeler' içeriyorsa False döner.
    Böylece 'masaj yapan el' videosunu eleriz.
    """
    text_to_check = (video_url + " " + " ".join(tags)).lower()
    
    for banned in BANNED_TERMS:
        if banned in text_to_check:
            print(f"🚫 Yasaklı video engellendi: {banned}")
            return False
    return True

# --- VİDEO KAYNAKLARI ---
def fetch_pexels_video(query):
    headers = {"Authorization": PEXELS_API_KEY}
    try:
        # Daha fazla sonuç iste (per_page=15) ki içinden eleme yapabilelim
        search_query = f"{query} dark horror cinematic"
        url = f"https://api.pexels.com/videos/search?query={search_query}&per_page=15&orientation=portrait"
        data = requests.get(url, headers=headers, timeout=5).json()
        
        videos = data.get("videos", [])
        if videos:
            random.shuffle(videos) # Hep ilk sıradakini alma
            for v in videos:
                # 1. KALİTE KONTROL (URL ve TAGS)
                video_url = v.get("url", "")
                video_tags = v.get("tags", [])
                
                if not is_safe_video(video_url, video_tags):
                    continue # Yasaklıysa sonraki videoya geç

                # 2. TEKNİK KONTROL
                files = v.get("video_files", [])
                suitable = [f for f in files if f["width"] >= 600]
                if suitable:
                    return sorted(suitable, key=lambda x: x["height"], reverse=True)[0]["link"]
    except: pass
    return None

def fetch_pixabay_video(query):
    try:
        if not PIXABAY_API_KEY: return None
        search_query = f"{query} dark"
        url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={search_query}&video_type=film&per_page=15" 
        data = requests.get(url, timeout=5).json()
        hits = data.get("hits", [])
        if hits:
            random.shuffle(hits)
            for hit in hits:
                # 1. KALİTE KONTROL (URL ve TAGS)
                video_url = hit.get("pageURL", "")
                video_tags = hit.get("tags", "")
                
                if not is_safe_video(video_url, [video_tags]):
                    continue

                if "large" in hit["videos"]: return hit["videos"]["large"]["url"]
                if "medium" in hit["videos"]: return hit["videos"]["medium"]["url"]
    except: pass
    return None

async def generate_resources(content):
    hook = content["hook"]
    script = content["script"]
    visual_queries = content["visual_queries"]
    
    # --- SES (V37 - SIKI MOD) ---
    communicate_hook = edge_tts.Communicate(hook, "en-US-ChristopherNeural", rate="-5%", pitch="-5Hz")
    await communicate_hook.save("hook.mp3")
    communicate_script = edge_tts.Communicate(script, "en-US-ChristopherNeural", rate="-5%", pitch="-5Hz")
    await communicate_script.save("script.mp3")
    
    hook_audio = AudioFileClip("hook.mp3")
    script_audio = AudioFileClip("script.mp3")
    silence = AudioClip(lambda t: [0, 0], duration=0.5, fps=44100) # +TTS = ~1.5s
    
    final_audio = concatenate_audioclips([hook_audio, silence, script_audio])
    final_audio.write_audiofile("voice.mp3")
    
    hook_audio.close()
    script_audio.close()
    if os.path.exists("hook.mp3"): os.remove("hook.mp3")
    if os.path.exists("script.mp3"): os.remove("script.mp3")

    audio = AudioFileClip("voice.mp3")
    
    # --- GÖRSEL ARAMA ---
    paths = []
    used_links = set()
    
    for query in visual_queries:
        if len(paths) * 2.5 > audio.duration: break
        
        video_link = None
        # Rastgele Pexels veya Pixabay dene
        if random.random() > 0.5:
            video_link = fetch_pixabay_video(query)
            if not video_link: video_link = fetch_pexels_video(query)
        else:
            video_link = fetch_pexels_video(query)
            if not video_link: video_link = fetch_pixabay_video(query)
            
        # Eğer spesifik video bulunamadıysa YEDEK LİSTEDEN al
        if not video_link:
             video_link = random.choice(FALLBACK_HORROR_VIDEOS)

        if video_link and video_link not in used_links:
            try:
                path = f"clip_{len(paths)}.mp4"
                with open(path, "wb") as f:
                    f.write(requests.get(video_link, timeout=15).content)
                
                c = VideoFileClip(path)
                if c.duration > 1.5:
                    paths.append(path)
                    used_links.add(video_link)
                c.close()
            except:
                if os.path.exists(path): os.remove(path)
    
    # Yeterli video yoksa dolgu yap
    while len(paths) * 2.0 < audio.duration:
        # Dolgu için de yasaklı kelime filtresi geçerli olan fonksiyonları kullanıyoruz
        video_link = fetch_pexels_video("abstract horror dark texture")
        if not video_link: video_link = random.choice(FALLBACK_HORROR_VIDEOS)

        if video_link and video_link not in used_links:
            path = f"clip_{len(paths)}.mp4"
            with open(path, "wb") as f:
                f.write(requests.get(video_link, timeout=15).content)
            paths.append(path)
            used_links.add(video_link)
        else:
            break

    return paths, audio

# --- GÖRSEL EFEKTLER (SABİT) ---
def cold_horror_grade(image):
    img_f = image.astype(float)
    gray = np.mean(img_f, axis=2, keepdims=True)
    desaturated = img_f * 0.4 + gray * 0.6
    tint_matrix = np.array([0.9, 1.0, 1.1])
    cold_img = desaturated * tint_matrix
    return np.clip(cold_img, 0, 255).astype(np.uint8)

def apply_processing(clip, duration):
    if clip.duration > duration:
        start = random.uniform(0, clip.duration - duration)
        clip = clip.subclip(start, start + duration)
    
    target_ratio = W / H
    if clip.w / clip.h > target_ratio:
        clip = clip.resize(height=H)
        clip = clip.crop(x1=clip.w/2 - W/2, width=W, height=H)
    else:
        clip = clip.resize(width=W)
        clip = clip.crop(y1=clip.h/2 - H/2, width=W, height=H)

    effect_type = random.choice(["zoom", "speed", "mirror", "none"])
    if effect_type == "speed":
        speed_factor = random.uniform(0.9, 1.1)
        clip = clip.fx(vfx.speedx, speed_factor)
    elif effect_type == "mirror":
        clip = clip.fx(vfx.mirror_x)
    elif effect_type == "zoom":
        clip = clip.resize(lambda t: 1 + 0.015 * t).set_position(('center', 'center'))

    clip = clip.fx(vfx.lum_contrast, contrast=0.15)
    clip = clip.fl_image(cold_horror_grade)
    return clip

# --- MONTAJ ---
def build_video(content):
    try:
        paths, audio = asyncio.run(generate_resources(content))
        if not paths: return None
            
        clips = []
        cur_dur = 0
        
        for p in paths:
            if cur_dur >= audio.duration: break
            try:
                c = VideoFileClip(p).without_audio()
                dur = random.uniform(2.0, 3.0) 
                processed = apply_processing(c, dur)
                clips.append(processed)
                cur_dur += processed.duration
            except: continue

        if not clips: return None

        final = concatenate_videoclips(clips, method="compose").set_audio(audio)
        if final.duration > audio.duration:
            final = final.subclip(0, audio.duration)
        
        out = "horror_v42_quality_control.mp4"
        final.write_videofile(out, fps=24, codec="libx264", preset="veryfast", bitrate="3500k", audio_bitrate="128k", threads=4, logger=None)
        
        audio.close()
        for c in clips: c.close()
        for p in paths: 
            if os.path.exists(p): os.remove(p)
        return out
    except Exception as e:
        print(f"Montaj hatası: {e}")
        return None

# --- TELEGRAM ---
@bot.message_handler(commands=["horror", "video"])
def handle(message):
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary story"
        
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\nKalite Kontrol Modu (V42)...")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ İçerik oluşturulamadı.", message.chat.id, msg.message_id)
            return

        bot.edit_message_text(f"🎬 **{content['title']}**\n🚫 'Mutlu' videolar engelleniyor.\n⏳ Render...", message.chat.id, msg.message_id)

        path = build_video(content)
        
        if path and os.path.exists(path):
            final_tags = f"{FIXED_HASHTAGS} {content['tags']}"
            
            caption_text = (
                f"🪝 **HOOK:**\n{content['hook']}\n\n"
                f"🎬 **Başlık:**\n{content['title']}\n\n"
                f"📝 **Hikaye:**\n{content['script']}\n\n"
                f"🏷️ **Açıklama:**\n{content['description']}\n\n"
                f"#️⃣ **Etiketler:**\n{final_tags}"
            )
            
            if len(caption_text) > 1000: caption_text = caption_text[:1000]
            
            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=caption_text)
        else:
            bot.edit_message_text("❌ Video render edilemedi.", message.chat.id, msg.message_id)
            
    except Exception as e:
        bot.reply_to(message, str(e))

if __name__ == "__main__":
    clean_start()
    bot.polling(non_stop=True)
