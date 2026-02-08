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

# --- YASAKLI KELİMELER (Mutlu videoları engelle) ---
BANNED_TERMS = [
    "happy", "smile", "laugh", "business", "corporate", "office", "working", 
    "family", "couple", "romantic", "wedding", "party", "celebration", 
    "wellness", "spa", "massage", "yoga", "relax", "calm", "bright", 
    "sunny", "beach", "holiday", "vacation", "funny", "cute", "baby"
]

# --- TEMİZLİK ---
def clean_start():
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except: pass

# --- AI İÇERİK (V45: STRICT VISUAL MATCH) ---
def get_content(topic):
    models = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-flash-latest", "gemini-2.5-flash"]
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    # PROMPT: Gemini'den HİKAYE AKIŞINA GÖRE SIRALI görsel listesi istiyoruz.
    prompt = (
        f"You are a viral horror shorts director. Write a script about '{topic}'. "
        "Strictly follow this format using '|||' as separator:\n"
        "CLICKBAIT TITLE (Max 4 words) ||| PUNCHY HOOK (Max 6 words) ||| SEO DESCRIPTION ||| NARRATION SCRIPT (60-70 words) ||| VISUAL_QUERIES_LIST ||| #tag1 #tag2 #tag3\n\n"
        "CRITICAL RULES:\n"
        "1. VISUAL_QUERIES_LIST: Give me exactly 12-15 search terms separated by commas. They must match the story chronologically. \n"
        "   - IF script says 'I saw a knife', query MUST be 'knife horror'.\n"
        "   - IF script says 'door opened', query MUST be 'opening door'.\n"
        "   - DO NOT give random abstract terms unless the story is abstract.\n"
        "2. LENGTH: 60-70 words (Target 30s).\n"
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

def is_safe_video(video_url, tags=[]):
    text_to_check = (video_url + " " + " ".join(tags)).lower()
    for banned in BANNED_TERMS:
        if banned in text_to_check:
            return False
    return True

# --- API ARAMA FONKSİYONLARI ---
def search_pexels(query):
    headers = {"Authorization": PEXELS_API_KEY}
    try:
        url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation=portrait"
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
        url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={query}&video_type=film&per_page=5" 
        data = requests.get(url, timeout=5).json()
        hits = data.get("hits", [])
        if hits:
            for hit in hits:
                if not is_safe_video(hit.get("pageURL", ""), [hit.get("tags", "")]): continue
                if "large" in hit["videos"]: return hit["videos"]["large"]["url"]
                if "medium" in hit["videos"]: return hit["videos"]["medium"]["url"]
    except: pass
    return None

# --- AKILLI ARAMA MOTORU (ASIL SİHİR BURADA) ---
def smart_search(query):
    """
    Bu fonksiyon 'Alakasız Video' sorununu çözer.
    Eğer tam cümleyi bulamazsa, kelimeleri azaltarak (basitleştirerek) arar.
    Asla rastgele video döndürmez.
    """
    # 1. Adım: Tam sorguyu dene (Örn: "bloody knife on wooden floor horror")
    # Pexels/Pixabay için "dark horror" eklemesini manuel yapıyoruz ama ana kelimeyi koruyoruz
    full_query = f"{query} dark horror"
    print(f"🔍 Aranıyor (Seviye 1): {full_query}")
    
    link = search_pexels(full_query)
    if not link: link = search_pixabay(full_query)
    if link: return link

    # 2. Adım: Bulamadı mı? Kelimeleri basitleştir.
    # Örn: "bloody knife floor" -> "knife horror"
    words = query.split()
    if len(words) > 1:
        # Ana nesneleri korumaya çalış (Basit bir mantıkla son kelimeyi veya ilk kelimeyi dene)
        # Genelde son kelimeler nesne olur (on the TABLE, inside the ROOM)
        simplified_query = f"{words[-1]} horror scary" 
        print(f"⚠️ Bulunamadı. Basitleştiriliyor (Seviye 2): {simplified_query}")
        
        link = search_pexels(simplified_query)
        if not link: link = search_pixabay(simplified_query)
        if link: return link
        
        # O da olmadıysa ilk kelimeyi dene (THE hand...)
        simplified_query_2 = f"{words[0]} horror scary"
        print(f"⚠️ Bulunamadı. Basitleştiriliyor (Seviye 3): {simplified_query_2}")
        
        link = search_pexels(simplified_query_2)
        if not link: link = search_pixabay(simplified_query_2)
        if link: return link

    # 3. Adım: Hala yoksa, gerçekten soyut bir şey ver ama hikayeden kopma.
    # Burası "yedek" değil, "atmosfer" aramasıdır.
    print(f"❌ Hiçbir şey bulunamadı. Atmosfer aranıyor.")
    fallback_query = "horror atmosphere dark cinematic"
    link = search_pexels(fallback_query)
    
    return link

# --- KAYNAK OLUŞTURMA ---
async def generate_resources(content):
    hook = content["hook"]
    script = content["script"]
    visual_queries = content["visual_queries"]
    
    # SES OLUŞTUR
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
    total_duration = audio.duration
    
    paths = []
    used_links = set()
    current_duration = 0.0
    
    # HER BİR SORGULAMA İÇİN VİDEO BUL (Sırasıyla)
    for query in visual_queries:
        if current_duration >= total_duration: break
        
        video_link = smart_search(query) # <--- Akıllı arama burada kullanılıyor
        
        if video_link and video_link not in used_links:
            try:
                path = f"clip_{len(paths)}.mp4"
                with open(path, "wb") as f:
                    f.write(requests.get(video_link, timeout=15).content)
                
                c = VideoFileClip(path)
                if c.duration > 1.5:
                    paths.append(path)
                    used_links.add(video_link)
                    # Her klibi montajda ortalama 2.5 saniye kullanacağız
                    current_duration += 2.5
                c.close()
            except:
                if os.path.exists(path): os.remove(path)

    # EĞER GEMINI AZ KELİME VERDİYSE VE SÜRE DOLMADIYSA
    # Listeyi başa sarıp, farklı videolar bulmaya çalış (Aynı konudan)
    loop_count = 0
    while current_duration < total_duration:
        if loop_count > 2: break # Sonsuz döngü koruması
        
        for query in visual_queries:
            if current_duration >= total_duration: break
            video_link = smart_search(f"{query} different angle") # Farklı açı iste
            
            if video_link and video_link not in used_links:
                try:
                    path = f"clip_{len(paths)}.mp4"
                    with open(path, "wb") as f:
                        f.write(requests.get(video_link, timeout=15).content)
                    paths.append(path)
                    used_links.add(video_link)
                    current_duration += 2.5
                except: pass
        loop_count += 1

    return paths, audio

# --- GÖRSEL EFEKTLER ---
def cold_horror_grade(image):
    img_f = image.astype(float)
    gray = np.mean(img_f, axis=2, keepdims=True)
    desaturated = img_f * 0.4 + gray * 0.6
    tint_matrix = np.array([0.9, 1.0, 1.1])
    cold_img = desaturated * tint_matrix
    return np.clip(cold_img, 0, 255).astype(np.uint8)

def apply_processing(clip, duration):
    # Loop veya Trim garantisi
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
        current_total_duration = 0.0
        
        # Klipleri ekle
        for p in paths:
            try:
                c = VideoFileClip(p).without_audio()
                # Her klibe rastgele bir süre ver (dinamiklik için)
                dur = random.uniform(2.0, 3.5) 
                processed = apply_processing(c, dur)
                clips.append(processed)
                current_total_duration += processed.duration
            except: continue

        # SÜRE YETMEZSE KOPYALA (DONMA GARANTİSİ)
        while current_total_duration < audio.duration:
            print("⚠️ Süre dolduruluyor...")
            random_clip = random.choice(clips).copy()
            random_clip = random_clip.fx(vfx.mirror_x) # Ayna efektiyle farklılaştır
            clips.append(random_clip)
            current_total_duration += random_clip.duration

        if not clips: return None

        final = concatenate_videoclips(clips, method="compose").set_audio(audio)
        if final.duration > audio.duration:
            final = final.subclip(0, audio.duration)
        
        out = "horror_v45_pro_match.mp4"
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
        
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\nProfesyonel Eşleşme Modu (V45)...")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ İçerik oluşturulamadı.", message.chat.id, msg.message_id)
            return

        bot.edit_message_text(f"🎬 **{content['title']}**\n🧠 Akıllı Arama Aktif\n⏳ Render...", message.chat.id, msg.message_id)

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
