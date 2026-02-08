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

# --- AYARLAR (RAILWAY) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
W, H = 720, 1280

# --- SABİT ETİKETLER ---
FIXED_HASHTAGS = "#horror #shorts #scary #creepy #mystery #fyp"

# --- TEMİZLİK ---
def clean_start():
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except: pass

# --- AI İÇERİK (V41: ATMOSFERİK BETİMLEMELER) ---
def get_content(topic):
    models = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-flash-latest", "gemini-2.5-flash"]
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    # PROMPT GÜNCELLEMESİ: DETAYLI GÖRSEL TARİFLERİ
    prompt = (
        f"You are a viral horror shorts director. Write a script about '{topic}'. "
        "Strictly follow this format using '|||' as separator:\n"
        "CLICKBAIT TITLE (Max 4 words) ||| PUNCHY HOOK (Max 6 words) ||| SEO DESCRIPTION ||| NARRATION SCRIPT (60-70 words) ||| VISUAL_QUERIES (15 TERMS) ||| #tag1 #tag2 #tag3\n\n"
        "CRITICAL RULES:\n"
        "1. VISUAL QUERIES: Provide exactly 15 chronological search terms. **CRITICAL: Do not use single words like 'hand' or 'door'. Describe the atmosphere and action.**\n"
        "   - BAD: 'hand', 'walking', 'eyes'\n"
        "   - GOOD: 'pale trembling hand reaching in dark', 'nervous feet walking on creaky wood floor', 'scary glowing eyes in shadow deep focus'\n"
        "2. SCRIPT LENGTH: 60-70 words (Target 30s).\n"
        "3. HOOK: Scary and spoken first.\n"
        "4. TAGS: Specific hashtags."
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
                        
                        # Güvenlik önlemi: Eğer 15'ten az geldiyse doldur
                        while len(visual_queries) < 15:
                            visual_queries.append("scary dark atmosphere cinematic")

                        data = {
                            "title": parts[0].strip(),
                            "hook": parts[1].strip(),
                            "description": parts[2].strip(),
                            "script": parts[3].strip(),
                            "visual_queries": visual_queries,
                            "tags": " ".join(valid_tags)
                        }
                        print(f"✅ İçerik alındı ({model})")
                        print(f"👀 Görsel Sorguları: {visual_queries}") # Konsoldan kontrol et
                        return data
        except: continue

    return None

# --- VİDEO KAYNAKLARI (GÜÇLENDİRİLMİŞ ARAMA) ---
def fetch_pexels_video(query):
    headers = {"Authorization": PEXELS_API_KEY}
    try:
        # Sorguyu daha da korkutucu hale getiriyoruz
        search_query = f"{query} scary horror cinematic dark atmosphere"
        url = f"https://api.pexels.com/videos/search?query={search_query}&per_page=3&orientation=portrait"
        data = requests.get(url, headers=headers, timeout=5).json()
        videos = data.get("videos", [])
        if videos:
            for v in videos:
                files = v.get("video_files", [])
                suitable = [f for f in files if f["width"] >= 600]
                if suitable:
                    return sorted(suitable, key=lambda x: x["height"], reverse=True)[0]["link"]
    except: pass
    return None

def fetch_pixabay_video(query):
    try:
        if not PIXABAY_API_KEY: return None
        # Sorguyu güçlendir
        search_query = f"{query} scary horror dark creepy"
        url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={search_query}&video_type=film&per_page=3" 
        data = requests.get(url, timeout=5).json()
        hits = data.get("hits", [])
        if hits:
            hit = random.choice(hits)
            if "large" in hit["videos"]: return hit["videos"]["large"]["url"]
            if "medium" in hit["videos"]: return hit["videos"]["medium"]["url"]
    except: pass
    return None

async def generate_resources(content):
    hook = content["hook"]
    script = content["script"]
    visual_queries = content["visual_queries"]
    
    # --- SES (V37 AYARLARI - 0.5s ES) ---
    communicate_hook = edge_tts.Communicate(hook, "en-US-ChristopherNeural", rate="-5%", pitch="-5Hz")
    await communicate_hook.save("hook.mp3")
    
    communicate_script = edge_tts.Communicate(script, "en-US-ChristopherNeural", rate="-5%", pitch="-5Hz")
    await communicate_script.save("script.mp3")
    
    hook_audio = AudioFileClip("hook.mp3")
    script_audio = AudioFileClip("script.mp3")
    silence = AudioClip(lambda t: [0, 0], duration=0.5, fps=44100)
    
    final_audio = concatenate_audioclips([hook_audio, silence, script_audio])
    final_audio.write_audiofile("voice.mp3")
    
    hook_audio.close()
    script_audio.close()
    if os.path.exists("hook.mp3"): os.remove("hook.mp3")
    if os.path.exists("script.mp3"): os.remove("script.mp3")

    audio = AudioFileClip("voice.mp3")
    
    # --- GÖRSEL ARAMA DÖNGÜSÜ ---
    paths = []
    used_links = set()
    
    for query in visual_queries:
        if len(paths) * 2.5 > audio.duration: break
        
        video_link = None
        if random.random() > 0.5:
            video_link = fetch_pixabay_video(query)
            if not video_link: video_link = fetch_pexels_video(query)
        else:
            video_link = fetch_pexels_video(query)
            if not video_link: video_link = fetch_pixabay_video(query)
            
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
    
    # Dolgu
    while len(paths) * 2.0 < audio.duration:
        fillers = ["scary dark atmosphere", "creepy shadow movement", "horror cinematic background"]
        video_link = fetch_pexels_video(random.choice(fillers))
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
        
        out = "horror_v41_atmospheric_visuals.mp4"
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
        
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\nAtmosferik Görsel Modu (V41)...")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ İçerik oluşturulamadı.", message.chat.id, msg.message_id)
            return

        bot.edit_message_text(f"🎬 **{content['title']}**\n🧠 Detaylı Sorgular: {content['visual_queries'][0]}, {content['visual_queries'][1]}...\n⏳ Render...", message.chat.id, msg.message_id)

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
