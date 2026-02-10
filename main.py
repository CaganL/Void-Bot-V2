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

# BS4 Koruması
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
    "shopping", "sale", "store", "market"
]

# --- GARANTİ KORKU SAHNELERİ ---
EMERGENCY_SCENES = [
    "dark shadow wall", "door handle turning", "broken mirror reflection", 
    "pale hand reaching", "person falling floor", "scary stairs", 
    "feet dragging", "glass breaking", "blood drip", "medical bandage",
    "bone fracture x-ray", "bruised skin", "teeth falling out", "eye close up scary"
]

# --- AI İÇERİK (V102: POV KASAP MODU - HİDRA MOTORLU) ---
def get_content(topic):
    # ÇALIŞAN TÜM MODELLER (HİDRA LİSTESİ)
    models = [
        "gemini-exp-1206", "gemini-2.5-pro", "gemini-2.5-flash", 
        "gemini-2.0-flash", "gemini-2.0-flash-001", "gemini-2.0-flash-lite-001",
        "gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro-latest", "gemini-flash-latest"
    ]
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    # --- PROMPT GÜNCELLEMESİ: V102 POV BUTCHER ---
    base_prompt = (
        f"You are a VICTIM describing your own physical trauma in a '{topic}'. "
        "Strictly follow this format using '|||' as separator:\n"
        "CLICKBAIT TITLE (High CTR) ||| PUNCHY HOOK (Sensory POV) ||| SEO DESCRIPTION ||| NARRATION SCRIPT (STRICTLY 40-60 WORDS) ||| VISUAL_SCENES_LIST ||| #tag1 #tag2 #tag3\n\n"
        "CRITICAL RULES (POV BUTCHER METHOD):\n"
        "1. **HOOK FORMULA:** Must be immediate sensory POV. 'I felt/heard [ACTION] at [LOCATION].'\n"
        "   - *Correct:* 'I felt a hand grab my ankle in the shower.'\n"
        "   - *Wrong:* 'I saw a body.' (Too passive)\n"
        "2. **PERSPECTIVE:** FIRST PERSON ONLY ('I', 'My leg', 'My spine'). Never use 'The subject'.\n"
        "3. **KINETIC CHAIN (THE COMBO):** Include an INTERMEDIATE IMPACT before death.\n"
        "   - *Structure:* Grab -> **Secondary Hit (Knee/Elbow)** -> Final Break.\n"
        "   - *Example:* 'Hand seized wrist. I pulled. **Elbow hit the sink.** Neck twisted. C1 snapped.'\n"
        "4. **STYLE:** Robotic Action. No emotions. No adjectives. Subject + Verb + Object."
    )
    
    print(f"🤖 Gemini'ye soruluyor: {topic}...")

    for i, current_model in enumerate(models):
        print(f"🔄 [{i+1}/{len(models)}] Deneniyor: {current_model}")
        payload = {"contents": [{"parts": [{"text": base_prompt}]}], "safetySettings": safety_settings}

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json=payload, timeout=20)
            
            if r.status_code == 429: continue
            if r.status_code == 404: continue

            if r.status_code == 200:
                response_json = r.json()
                if 'candidates' in response_json and response_json['candidates']:
                    raw_text = response_json['candidates'][0]['content']['parts'][0]['text']
                    parts = raw_text.split("|||")
                    
                    if len(parts) >= 6:
                        script_text = parts[3].strip()
                        hook_text = parts[1].strip()
                        if script_text.lower().startswith(hook_text.lower()):
                            script_text = script_text[len(hook_text):].strip()

                        word_count = len(script_text.split())
                        print(f"✅ ZAFER! {current_model} başardı: {word_count} Kelime")

                        # KELİME KONTROLÜ (Duygu Yasak, POV Zorunlu)
                        if any(f in script_text.lower() for f in ["scared", "froze", "felt fear", "subject"]):
                             print("❌ Yasaklı kelime (Duygu veya 'Subject'). Pas geçiliyor...")
                             continue
                        
                        raw_tags = parts[5].strip().replace(",", " ").split()
                        raw_queries = parts[4].split(",")
                        visual_queries = [v.strip().lower() for v in raw_queries if len(v.strip()) > 1]
                        
                        if len(visual_queries) < 12:
                            visual_queries.extend(EMERGENCY_SCENES)
                            random.shuffle(visual_queries)
                            visual_queries = list(dict.fromkeys(visual_queries))[:20]

                        return {
                            "title": parts[0].strip(),
                            "hook": hook_text,
                            "description": parts[2].strip(),
                            "script": script_text,
                            "visual_queries": visual_queries,
                            "tags": " ".join([t for t in raw_tags if t.startswith("#")])
                        }
        except Exception: continue

    return None

def is_safe_video(video_url, tags=[]):
    text_to_check = (video_url + " " + " ".join(tags)).lower()
    for b in BANNED_TERMS:
        if b in text_to_check: return False
    return True

# --- ARAMA MOTORLARI ---
def search_mixkit(query):
    if not BS4_AVAILABLE: return None
    try:
        search_url = f"https://mixkit.co/free-stock-video/{query.replace(' ', '-')}/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(search_url, headers=headers, timeout=5)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.text, 'html.parser')
        videos = soup.find_all('video')
        if not videos: return None
        return videos[0].get('src')
    except: pass
    return None

def search_pexels(query):
    headers = {"Authorization": PEXELS_API_KEY}
    try:
        enhanced_query = f"{query} dark horror"
        url = f"https://api.pexels.com/videos/search?query={enhanced_query}&per_page=5&orientation=portrait"
        data = requests.get(url, headers=headers, timeout=5).json()
        videos = data.get("videos", [])
        if videos:
            for v in videos:
                if not is_safe_video(v.get("url", ""), v.get("tags", [])): continue
                files = v.get("video_files", [])
                suitable = [f for f in files if f["width"] >= 600]
                if suitable:
                    return sorted(suitable, key=lambda x: x["height"], reverse=True)[0]["link"]
    except: pass
    return None

def search_pixabay(query):
    if not PIXABAY_API_KEY: return None
    try:
        enhanced_query = f"{query} horror"
        url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={enhanced_query}&video_type=film&per_page=5" 
        data = requests.get(url, timeout=5).json()
        hits = data.get("hits", [])
        if hits:
            for hit in hits:
                if not is_safe_video(hit.get("pageURL", ""), [hit.get("tags", "")]): continue
                if "large" in hit["videos"]: return hit["videos"]["large"]["url"]
                if "medium" in hit["videos"]: return hit["videos"]["medium"]["url"]
    except: pass
    return None

def smart_scene_search(query):
    link = search_mixkit(query)
    if not link: link = search_pexels(query)
    if not link: link = search_pixabay(query)
    if link: return link

    words = query.split()
    if len(words) > 2:
        simple_query = " ".join(words[-2:])
        link = search_pexels(simple_query)
        if not link: link = search_pixabay(simple_query)
        if link: return link

    if len(words) > 0:
        noun_query = words[-1]
        link = search_pexels(noun_query)
        if link: return link
    return None

# --- KAYNAK OLUŞTURMA ---
async def generate_resources(content):
    hook = content["hook"]
    script = content["script"]
    visual_queries = content["visual_queries"]
    
    try:
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
    except Exception as e:
        print(f"TTS Hatası: {e}")
        return None

    audio = AudioFileClip("voice.mp3")
    total_duration = audio.duration
    
    paths = []
    used_links = set()
    current_duration = 0.0
    
    for query in visual_queries:
        if current_duration >= total_duration: break
        video_link = smart_scene_search(query)
        
        if video_link and video_link not in used_links:
            try:
                path = f"clip_{len(paths)}.mp4"
                for _ in range(3):
                    try:
                        r = requests.get(video_link, timeout=15)
                        if r.status_code == 200:
                            with open(path, "wb") as f: f.write(r.content)
                            break
                    except: time.sleep(1)

                if os.path.exists(path) and os.path.getsize(path) > 1000:
                    c = VideoFileClip(path)
                    if c.duration > 1.0:
                        paths.append(path)
                        used_links.add(video_link)
                        current_duration += 2.5
                    c.close()
            except:
                if os.path.exists(path): os.remove(path)

    if not paths: return None
    return paths, audio

# --- EFEKTLER ---
def cold_horror_grade(image):
    img_f = image.astype(float)
    gray = np.mean(img_f, axis=2, keepdims=True)
    desaturated = img_f * 0.3 + gray * 0.7 
    tint_matrix = np.array([0.9, 1.0, 1.1])
    cold_img = desaturated * tint_matrix
    cold_img = cold_img * 0.6 
    return np.clip(cold_img, 0, 255).astype(np.uint8)

def apply_processing(clip, duration):
    if clip.duration < duration:
        clip = vfx.loop(clip, duration=duration)
    else:
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
        clip = clip.fx(vfx.speedx, random.uniform(0.9, 1.1))
    elif effect_type == "mirror":
        clip = clip.fx(vfx.mirror_x)
    elif effect_type == "zoom":
        clip = clip.resize(lambda t: 1 + 0.02 * t).set_position(('center', 'center'))

    clip = clip.fl_image(cold_horror_grade)
    return clip

# --- MONTAJ ---
def build_video(content):
    try:
        res = asyncio.run(generate_resources(content))
        if not res: return None
        paths, audio = res
            
        clips = []
        current_total_duration = 0.0
        
        for p in paths:
            try:
                c = VideoFileClip(p).without_audio()
                dur = random.uniform(2.0, 3.5)
                processed = apply_processing(c, dur)
                clips.append(processed)
                current_total_duration += processed.duration
            except: continue

        while current_total_duration < audio.duration:
            random_clip = random.choice(clips).copy()
            random_clip = random_clip.fx(vfx.mirror_x)
            clips.append(random_clip)
            current_total_duration += random_clip.duration

        final = concatenate_videoclips(clips, method="compose").set_audio(audio)
        if final.duration > audio.duration:
            final = final.subclip(0, audio.duration)
        
        out = "horror_v102_pov_butcher.mp4"
        final.write_videofile(out, fps=24, codec="libx264", preset="veryfast", bitrate="3000k", audio_bitrate="128k", threads=4, logger=None)
        
        audio.close()
        for c in clips: c.close()
        for p in paths: 
            if os.path.exists(p): os.remove(p)
        return out
    except Exception as e:
        print(f"Montaj hatası: {e}")
        return None

@bot.message_handler(commands=["horror", "video"])
def handle(message):
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary story"
        
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\nPOV Kasap Modu (V102)...\n")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ İçerik üretilemedi.", message.chat.id, msg.message_id)
            return

        bot.edit_message_text(f"🎬 **{content['title']}**\n👁️ POV Bakış Açısı Aktif\n⏳ Render...", message.chat.id, msg.message_id)

        path = build_video(content)
        
        if path and os.path.exists(path):
            final_tags = f"{FIXED_HASHTAGS} {content['tags']}"
            caption_text = (
                f"🪝 **HOOK:**\n{content['hook']}\n\n"
                f"🎬 **Başlık:**\n{content['title']}\n\n"
                f"📝 **Hikaye:**\n{content['script']}\n\n"
                f"#️⃣ **Etiketler:**\n{final_tags}"
            )
            if len(caption_text) > 1000: caption_text = caption_text[:1000]
            
            # V100 GÜVENLİ YÜKLEME (Korundu)
            bot.edit_message_text("📤 Yükleniyor...", message.chat.id, msg.message_id)
            sent = False
            for attempt in range(3):
                try:
                    with open(path, "rb") as v:
                        bot.send_video(message.chat.id, v, caption=caption_text, timeout=600)
                    sent = True
                    break
                except Exception as e:
                    print(f"Yükleme hatası (Deneme {attempt+1}): {e}")
                    time.sleep(5)
            
            if not sent:
                bot.reply_to(message, "❌ Yükleme zaman aşımına uğradı.")
                
        else:
            bot.edit_message_text("❌ Video render edilemedi.", message.chat.id, msg.message_id)
            
    except Exception as e:
        bot.reply_to(message, f"Hata: {str(e)}")

if __name__ == "__main__":
    print("Bot başlatılıyor...")
    bot.polling(non_stop=True)
