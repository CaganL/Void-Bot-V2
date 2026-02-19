import os
import telebot
import requests
import random
import time
import numpy as np
from moviepy.editor import (
    VideoFileClip, AudioFileClip, concatenate_videoclips, vfx, concatenate_audioclips
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

ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "ErXwobaYiN019PkySvjV") 

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
W, H = 720, 1280

# --- SABİT ETİKETLER & YASAKLI KELİMELER ---
FIXED_HASHTAGS = "#horror #shorts #scary #creepy #mystery #fyp"
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
        "3. STYLE: Cold, Clinical."
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

# --- STOK VİDEO ARAMA ---
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
    link = search_pexels(query)
    if not link: link = search_mixkit(query) 
    return link

# --- SES MOTORU: ELEVENLABS ---
def generate_elevenlabs_audio(text, filename):
    if not ELEVENLABS_API_KEY: 
        print("❌ ElevenLabs API Anahtarı eksik!", flush=True)
        return False
        
    print(f"🎙️ ElevenLabs'ten ses isteniyor: {filename}...", flush=True)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": ELEVENLABS_API_KEY}
    data = {"text": text, "model_id": "eleven_turbo_v2_5", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
    
    try:
        r = requests.post(url, json=data, headers=headers, timeout=30)
        if r.status_code == 200:
            with open(filename, 'wb') as f: f.write(r.content)
            print(f"✅ Başarılı: {filename} oluşturuldu.", flush=True)
            return True
        else:
            print(f"❌ ElevenLabs Hatası: {r.status_code} - {r.text}", flush=True)
            return False
    except Exception as e: 
        print(f"❌ ElevenLabs Bağlantı Hatası: {e}", flush=True)
        return False

# --- KAYNAK OLUŞTURMA ---
def generate_resources(content):
    hook = content["hook"]
    script = content["script"]
    visual_queries = content["visual_queries"]
    
    if not generate_elevenlabs_audio(hook, "hook.mp3"): return None
    if not generate_elevenlabs_audio(script, "script.mp3"): return None

    try:
        print("🎧 Sesler birleştiriliyor...", flush=True)
        h_audio = AudioFileClip("hook.mp3")
        s_audio = AudioFileClip("script.mp3")
        
        final_audio = concatenate_audioclips([h_audio, s_audio])
        final_audio.write_audiofile("voice.mp3", logger=None)
        
        h_audio.close()
        s_audio.close()
        
        if os.path.exists("hook.mp3"): os.remove("hook.mp3")
        if os.path.exists("script.mp3"): os.remove("script.mp3")
        print("✅ Ses montajı tamam.", flush=True)
    except Exception as e:
        print(f"❌ Ses birleştirme hatası: {e}", flush=True)
        return None

    print("🎬 Videolar indiriliyor...", flush=True)
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
    
    if not paths: 
        print("❌ Hiç video indirilemedi!", flush=True)
        return None
        
    print(f"✅ Toplam {len(paths)} video indirildi.", flush=True)
    return paths, final_audio

# --- KESME VE BOYUTLANDIRMA (Efektsiz) ---
def apply_processing(clip, duration):
    # Eğer video süresi kısa ise uzat, uzun ise rastgele bir yerinden kes
    if clip.duration < duration:
        clip = vfx.loop(clip, duration=duration)
    else:
        start = random.uniform(0, clip.duration - duration)
        clip = clip.subclip(start, start + duration)
    
    # 720x1280 (WxH) formatına tam oturtmak için kırpma
    if clip.w/clip.h > W/H:
        clip = clip.resize(height=H).crop(x1=clip.w/2-W/2, width=W, height=H)
    else:
        clip = clip.resize(width=W).crop(y1=clip.h/2-H/2, width=W, height=H)

    # Hiçbir renk filtresi yok, ham görüntüyü döndür
    return clip

# --- MONTAJ ---
def build_video(content):
    try:
        res = generate_resources(content) 
        if not res: return None
        paths, audio = res
            
        print("🎞️ Video montajı (render) başlıyor...", flush=True)
        clips = []
        for p in paths:
            try:
                c = VideoFileClip(p).without_audio()
                dur = random.uniform(2.5, 3.5)
                clips.append(apply_processing(c, dur))
            except Exception as e:
                print(f"❌ Klip işleme hatası: {e}", flush=True)
                continue

        # Sesin süresini tam doldurmak için son klibi uzat (RAM dostu yöntem)
        total_video_dur = sum(c.duration for c in clips)
        if clips and total_video_dur < audio.duration:
            missing_dur = audio.duration - total_video_dur
            last_clip = clips[-1]
            extended_last = vfx.loop(last_clip, duration=last_clip.duration + missing_dur)
            clips[-1] = extended_last

        print("⚙️ Klipler birleştiriliyor...", flush=True)
        final = concatenate_videoclips(clips, method="compose").set_audio(audio)
        final = final.subclip(0, audio.duration)
        
        out = "final_output.mp4"
        print("💾 Dosyaya yazılıyor (Efektsiz, Hızlı Render)...", flush=True)
        
        # Bitrate 2000k olarak korundu
        final.write_videofile(out, fps=24, codec="libx264", preset="ultrafast", bitrate="2000k", audio_bitrate="128k", threads=1, logger=None)
        
        audio.close()
        for c in clips: c.close()
        final.close() 
        for p in paths: 
            if os.path.exists(p): os.remove(p)
            
        print("✅ Render başarıyla tamamlandı!", flush=True)
        return out
    except Exception as e:
        print(f"❌ Montaj Hatası: {e}", flush=True)
        return None

# --- TELEGRAM BOT KOMUTLARI ---
@bot.message_handler(commands=["horror", "video"])
def handle(message):
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary story"
        
        print(f"\n--- YENİ TALEP GELDİ: {topic} ---", flush=True)
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\nElevenLabs HD Modu Devrede...\n")
        
        content = get_content(topic)
        
        if not content:
            bot.edit_message_text("❌ İçerik üretilemedi.", message.chat.id, msg.message_id)
            print("❌ Gemini içerik üretemedi.", flush=True)
            return

        bot.edit_message_text(f"🎬 **{content['title']}**\n🎙️ Ses: ElevenLabs\n📍 Mekan: {content['location'].upper()}\n⏳ Render İşlemi Başladı...", message.chat.id, msg.message_id)

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

            with open(path, "rb") as v:
                bot.send_video(message.chat.id, v, caption=caption_text, timeout=600)
                
            os.remove(path)
            if os.path.exists("voice.mp3"): os.remove("voice.mp3")
            print("✅ Video başarıyla Telegram'a gönderildi.", flush=True)
        else:
            bot.edit_message_text("❌ Render hatası. Videoyu oluştururken bir sorun yaşandı.", message.chat.id, msg.message_id)
            print("❌ Süreç tamamlanamadı.", flush=True)
            
    except Exception as e:
        bot.reply_to(message, f"Bot Hatası: {e}")
        print(f"❌ Kritik Bot Hatası: {e}", flush=True)

if __name__ == "__main__":
    print("Bot başlatılıyor... Efektsiz HD Sürüm aktif.", flush=True)
    bot.polling(non_stop=True)
