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

# BS4 Korumalı Import (Hata verirse kod çökmesin diye)
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("⚠️ UYARI: beautifulsoup4 yüklü değil! Mixkit devre dışı kalacak.")

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
W, H = 720, 1280

# --- SABİT ETİKETLER ---
FIXED_HASHTAGS = "#horror #shorts #scary #creepy #mystery #fyp"

# --- AI İÇERİK (V48: SADECE NESNE İSİMLERİ) ---
def get_content(topic):
    models = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-flash-latest", "gemini-2.5-flash"]
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    # PROMPT DEĞİŞİKLİĞİ: "TEK KELİME NESNE"
    # Gemini'ye diyoruz ki: Bana "korkunç karanlık orman" deme. Sadece "Orman" de.
    # Biz onu kodla karartacağız. Sıfatlar arama motorunu şaşırtıyor.
    prompt = (
        f"You are a viral horror shorts director. Write a script about '{topic}'. "
        "Strictly follow this format using '|||' as separator:\n"
        "CLICKBAIT TITLE (Max 4 words) ||| PUNCHY HOOK (Max 6 words) ||| SEO DESCRIPTION ||| NARRATION SCRIPT (50-60 words) ||| VISUAL_QUERIES_LIST ||| #tag1 #tag2 #tag3\n\n"
        "CRITICAL RULES:\n"
        "1. VISUAL_QUERIES_LIST: Give me exactly 12-15 search terms. \n"
        "   - **EXTREMELY IMPORTANT**: USE ONLY NOUNS (OBJECTS). DO NOT USE ADJECTIVES.\n"
        "   - BAD: 'scary dark hallway', 'running frightened man', 'creepy eye'\n"
        "   - GOOD: 'hallway', 'feet running', 'eye macro', 'door handle', 'forest'\n"
        "   - REASON: We need exact stock footage matches.\n"
        "2. LENGTH: Script must be 50-60 words.\n"
        "3. HOOK: Scary and spoken first. DO NOT REPEAT HOOK IN SCRIPT."
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
            
            if r.status_code == 200:
                response_json = r.json()
                if 'candidates' in response_json and response_json['candidates']:
                    raw_text = response_json['candidates'][0]['content']['parts'][0]['text']
                    parts = raw_text.split("|||")
                    
                    if len(parts) >= 6:
                        raw_tags = parts[5].strip().replace(",", " ").split()
                        valid_tags = [t for t in raw_tags if t.startswith("#")]
                        visual_queries = [v.strip().lower() for v in parts[4].split(",")] # Küçük harfe çevir
                        
                        hook_text = parts[1].strip()
                        script_text = parts[3].strip()
                        if script_text.lower().startswith(hook_text.lower()):
                            script_text = script_text[len(hook_text):].strip()

                        data = {
                            "title": parts[0].strip(),
                            "hook": hook_text,
                            "description": parts[2].strip(),
                            "script": script_text,
                            "visual_queries": visual_queries,
                            "tags": " ".join(valid_tags)
                        }
                        print(f"✅ İçerik alındı ({model})")
                        print(f"🔍 Arama Terimleri: {visual_queries}")
                        return data
        except: continue

    return None

# --- MIXKIT SCRAPER (BS4 Korumalı) ---
def search_mixkit(query):
    if not BS4_AVAILABLE: return None
    try:
        # Mixkit'te sıfat eklemeden arıyoruz
        search_url = f"https://mixkit.co/free-stock-video/{query.replace(' ', '-')}/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(search_url, headers=headers, timeout=5)
        if response.status_code != 200: return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        videos = soup.find_all('video')
        if not videos: return None
        
        # En üstteki videoyu al (En alakalı olan)
        video = videos[0] 
        video_src = video.get('src')
        if video_src: return video_src
    except: pass
    return None

# --- PEXELS (Sıfatsız Arama) ---
def search_pexels(query):
    headers = {"Authorization": PEXELS_API_KEY}
    try:
        # BURASI ÖNEMLİ: "Dark horror" eklemiyoruz. Sadece nesneyi arıyoruz.
        # "Hallway" ararsan koridor çıkar. "Horror hallway" ararsan bazen saçma şeyler çıkar.
        url = f"https://api.pexels.com/videos/search?query={query}&per_page=3&orientation=portrait"
        data = requests.get(url, headers=headers, timeout=5).json()
        videos = data.get("videos", [])
        if videos:
            # RASTGELE YOK! En alakalı (0. indeks) videoyu alıyoruz.
            v = videos[0] 
            files = v.get("video_files", [])
            suitable = [f for f in files if f["width"] >= 600]
            if suitable:
                return sorted(suitable, key=lambda x: x["height"], reverse=True)[0]["link"]
    except: pass
    return None

# --- PIXABAY (Sıfatsız Arama) ---
def search_pixabay(query):
    if not PIXABAY_API_KEY: return None
    try:
        url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={query}&video_type=film&per_page=3" 
        data = requests.get(url, timeout=5).json()
        hits = data.get("hits", [])
        if hits:
            # En alakalı videoyu al
            hit = hits[0]
            if "large" in hit["videos"]: return hit["videos"]["large"]["url"]
            if "medium" in hit["videos"]: return hit["videos"]["medium"]["url"]
    except: pass
    return None

# --- AVCI MODU V2 (Basitleştirilmiş) ---
def sniper_search(query):
    print(f"🎯 Hedef: {query}")
    
    # 1. Mixkit (En iyi kalite)
    link = search_mixkit(query)
    if link: 
        print(f"✅ Mixkit vurdu: {query}")
        return link
        
    # 2. Pexels (Saf arama)
    link = search_pexels(query)
    if link: return link
    
    # 3. Pixabay (Saf arama)
    link = search_pixabay(query)
    if link: return link
    
    # 4. Bulunamadıysa kelimeyi parçala (Son çare)
    # "Wooden Door" -> "Door"
    words = query.split()
    if len(words) > 1:
        simple_query = words[-1] # Genelde nesne sondadır
        print(f"⚠️ Basitleştiriliyor: {simple_query}")
        link = search_pexels(simple_query)
        if link: return link

    print("❌ Iskaladı. Siyah ekran geçilecek (Alakasız video koymamak için).")
    return None

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
    
    # VİDEO ARAMA
    for query in visual_queries:
        if current_duration >= total_duration: break
        
        video_link = sniper_search(query)
        
        if video_link and video_link not in used_links:
            try:
                path = f"clip_{len(paths)}.mp4"
                with open(path, "wb") as f:
                    f.write(requests.get(video_link, timeout=15).content)
                
                c = VideoFileClip(path)
                if c.duration > 1.5:
                    paths.append(path)
                    used_links.add(video_link)
                    current_duration += 2.5
                c.close()
            except:
                if os.path.exists(path): os.remove(path)

    # LOOP (Sadece bulunan alakalı videoları tekrar et)
    loop_count = 0
    while current_duration < total_duration:
        if not paths: break # Hiç video bulamadıysa yapacak bir şey yok
        if loop_count > 10: break # Güvenlik
        
        # Eldeki alakalı videolardan rastgele seç (Yeniden indirme, kopyala)
        # Burası montaj kısmında halledilecek, sadece sayaç için
        current_duration += 2.5
        loop_count += 1

    return paths, audio

# --- GÖRSEL EFEKTLER (KARANLIKLAŞTIRMA BURADA YAPILIYOR) ---
def cold_horror_grade(image):
    # Görüntüyü kodla karartıyoruz, böylece "Mutlu Koridor" videosu "Korkunç Koridor" oluyor.
    img_f = image.astype(float)
    gray = np.mean(img_f, axis=2, keepdims=True)
    # Doygunluğu düşür, biraz mavi ekle
    desaturated = img_f * 0.3 + gray * 0.7 
    tint_matrix = np.array([0.8, 0.9, 1.0]) # Maviye çal
    cold_img = desaturated * tint_matrix
    
    # Ekstra Karanlık (Gamma)
    cold_img = cold_img * 0.7 # Parlaklığı %30 düşür
    
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

    # Efektler
    effect_type = random.choice(["zoom", "speed", "mirror", "none"])
    if effect_type == "speed":
        clip = clip.fx(vfx.speedx, random.uniform(0.9, 1.1))
    elif effect_type == "mirror":
        clip = clip.fx(vfx.mirror_x)
    elif effect_type == "zoom":
        clip = clip.resize(lambda t: 1 + 0.02 * t).set_position(('center', 'center'))

    # Renk efekti
    clip = clip.fl_image(cold_horror_grade)
    return clip

# --- MONTAJ ---
def build_video(content):
    try:
        paths, audio = asyncio.run(generate_resources(content))
        if not paths: 
            print("❌ Hiç video bulunamadı!")
            return None
            
        clips = []
        current_total_duration = 0.0
        
        # İndirilenleri ekle
        for p in paths:
            try:
                c = VideoFileClip(p).without_audio()
                dur = random.uniform(2.0, 3.5)
                processed = apply_processing(c, dur)
                clips.append(processed)
                current_total_duration += processed.duration
            except: continue

        # SÜRE YETMEZSE ELDEKİLERİ KOPYALA
        # Alakasız video indirmek yerine, alakalı olanı tekrar kullanmak daha iyidir.
        while current_total_duration < audio.duration:
            random_clip = random.choice(clips).copy()
            random_clip = random_clip.fx(vfx.mirror_x) # Ayna yap ki fark edilmesin
            # Hızını değiştir
            random_clip = random_clip.fx(vfx.speedx, 0.8) 
            clips.append(random_clip)
            current_total_duration += random_clip.duration

        final = concatenate_videoclips(clips, method="compose").set_audio(audio)
        if final.duration > audio.duration:
            final = final.subclip(0, audio.duration)
        
        out = "horror_v48_sniper.mp4"
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
        
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\nNesne Odaklı Mod (V48)...")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ İçerik oluşturulamadı.", message.chat.id, msg.message_id)
            return
            
        # Kullanıcıya hangi kelimeleri aradığımızı gösterelim ki içi rahat etsin
        search_terms_preview = ", ".join(content['visual_queries'][:4])
        bot.edit_message_text(f"🎬 **{content['title']}**\n🔍 Aranıyor: {search_terms_preview}...\n⏳ Render...", message.chat.id, msg.message_id)

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
            bot.edit_message_text("❌ Video oluşturulamadı (Kaynak bulunamadı).", message.chat.id, msg.message_id)
            
    except Exception as e:
        bot.reply_to(message, f"Hata: {str(e)}")

if __name__ == "__main__":
    print("Bot başlatılıyor...")
    bot.polling(non_stop=True)
