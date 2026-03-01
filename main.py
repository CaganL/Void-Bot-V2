import os
import random
import telebot
import requests
import subprocess
import yt_dlp
import imageio_ffmpeg

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

VOICES = {
    "david": "kaGxVtjLwllv1bi2GFag"
}
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", VOICES["david"]) 

PLAYLIST_URL = "https://youtube.com/playlist?list=PL4LOQK13CVLklHJF2kOn0jdcaSQSrgsRY"

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
FIXED_HASHTAGS = "#horror #shorts #scary #creepy #mystery #fyp"

# --- GEMINI: SENARYO OLUŞTURMA ---
def get_content(topic):
    models = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-exp-1206"]
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]

    base_prompt = (
        f"Write a psychological horror short script about: '{topic}'. "
        "Strictly follow this exact format using '|||' as separator:\n"
        "CLICKBAIT TITLE (1st Person POV ONLY) ||| PUNCHY HOOK (STRICTLY 2 TO 6 WORDS MAX) ||| SEO DESCRIPTION ||| NARRATION SCRIPT (55-65 WORDS) ||| 3_UNIQUE_SEARCH_VARIANTS ||| #tags (Max 3 unique tags)\n\n"
        "RULES:\n"
        "1. NO GORE. Build fear through tech paranoia and physical space invasion.\n"
        "2. ZERO THOUGHTS, ZERO LOGIC. Write ONLY raw, cold sights and sounds.\n"
        "3. THE HOOK: STRICTLY MAXIMUM 6 WORDS.\n"
        "4. DO NOT repeat the Hook in the Narration Script.\n"
        "5. POV RULE: 1st person ('I', 'My') ONLY."
    )
    
    for current_model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json={"contents": [{"parts": [{"text": base_prompt}]}], "safetySettings": safety_settings}, timeout=20)
            if r.status_code == 200:
                raw_text = r.json()['candidates'][0]['content']['parts'][0]['text']
                parts = raw_text.split("|||")
                if len(parts) >= 6:
                    return {
                        "title": parts[0].strip(),
                        "hook": parts[1].strip(),
                        "script": parts[3].strip(),
                        "tags": parts[5].strip()
                    }
        except Exception:
            continue
    return None

def generate_elevenlabs_audio(text, filename):
    if not ELEVENLABS_API_KEY: return False
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": ELEVENLABS_API_KEY}
    data = {"text": text, "model_id": "eleven_turbo_v2_5", "voice_settings": {"stability": 0.52, "similarity_boost": 0.85, "style": 0.10}}
    try:
        r = requests.post(url, json=data, headers=headers, timeout=30)
        if r.status_code == 200:
            with open(filename, 'wb') as f: f.write(r.content)
            return True
    except Exception: 
        return False
    return False

# --- YENİ DEVRİM: SIFIR İNDİRME, CANLI YAYIN ÇEKME MOTORU ---
def get_direct_stream_url():
    # 1. Oynatma listesindeki videoların sadece linklerini çok hızlıca listele
    ydl_opts_flat = {
        'extract_flat': True,
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts_flat) as ydl:
        info = ydl.extract_info(PLAYLIST_URL, download=False)
        if 'entries' in info:
            entries = list(info['entries'])
            random_entry = random.choice(entries)
            video_url = random_entry.get('url') or random_entry.get('webpage_url')
        else:
            video_url = PLAYLIST_URL 
            
    # 2. Seçtiğimiz tek videonun gizli yayın linkini ve süresini al (Sesi umursama bile, sadece görüntü!)
    ydl_opts_info = {
        'format': 'bestvideo[height<=720][ext=mp4]/best[height<=720][ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
        vid_info = ydl.extract_info(video_url, download=False)
        direct_url = vid_info['url'] # Bu bizim sihirli canlı yayın linkimiz
        duration = vid_info.get('duration', 60)
        return direct_url, duration

# --- FFMPEG: CANLI MONTAJ ---
def create_final_video(audio_file, output_file):
    try:
        # İnternetten direkt linki al
        direct_url, duration = get_direct_stream_url()
        
        # Videonun rastgele bir saniyesine zıplayalım (Son 60 saniyeye girmeden)
        max_start = max(0, duration - 60)
        start_time = random.randint(0, int(max_start)) if max_start > 0 else 0
        
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        
        cmd = [
            ffmpeg_exe, "-y",
            "-ss", str(start_time),  # YouTube sunucusuna "Videoyu bana şu saniyeden itibaren ver" diyoruz
            "-i", direct_url,        # İNDİRME YOK! Görüntüyü havada yakalıyoruz
            "-i", audio_file,        # Kendi ses dosyamız
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264",             
            "-preset", "veryfast",        
            "-crf", "28",                  
            "-pix_fmt", "yuv420p",         
            "-c:a", "aac",                 
            "-shortest",             # EN KRİTİK KOMUT: Senin dediğin gibi ses bittiği an (örn 27. sn) bağlantıyı kes!
            "-map", "0:v:0",
            "-map", "1:a:0",
            output_file
        ]
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return False, f"FFmpeg Hatası: {result.stderr[-300:]}"
            
        return True, "Başarılı"
    except Exception as e:
        return False, f"Yayın Çekme Hatası: {str(e)}"

# --- TELEGRAM BOT KOMUTLARI ---
@bot.message_handler(commands=["horror", "video"])
def handle(message):
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "scary story"
        
        msg = bot.reply_to(message, f"💀 **{topic.upper()}**\n📝 Senaryo yazılıyor...")
        content = get_content(topic)
        if not content:
            bot.edit_message_text("❌ İçerik üretilemedi.", message.chat.id, msg.message_id)
            return

        bot.edit_message_text(f"🎬 **{content['title']}**\n🎙️ Seslendiriliyor ve YouTube'dan saniyesi saniyesine canlı yayın çekiliyor...", message.chat.id, msg.message_id)

        hook_text = content['hook']
        script_text = content['script']
        if script_text.lower().startswith(hook_text.lower()):
            script_text = script_text[len(hook_text):].strip().lstrip(".,?! -")
            
        full_audio_text = f"{hook_text} ... {script_text}"
        
        audio_filename = "final_voice.mp3"
        video_filename = "final_video.mp4"

        if os.path.exists(audio_filename): os.remove(audio_filename)
        if os.path.exists(video_filename): os.remove(video_filename)

        if generate_elevenlabs_audio(full_audio_text, audio_filename):
            
            video_success, v_error = create_final_video(audio_filename, video_filename)
            
            caption_text = (
                f"🪝 **HOOK:**\n{hook_text}\n\n"
                f"🎬 **BAŞLIK:**\n{content['title']}\n\n"
                f"📝 **HİKAYE:**\n{script_text}\n\n"
                f"#️⃣ **ETİKETLER:**\n{FIXED_HASHTAGS} {content['tags']}"
            )
            if len(caption_text) > 1000: caption_text = caption_text[:1000]

            if video_success and os.path.exists(video_filename):
                with open(video_filename, "rb") as video:
                    bot.send_video(message.chat.id, video, caption=caption_text, timeout=120)
                os.remove(video_filename)
            else:
                hata_mesaji = f"⚠️ Video oluşturulamadı.\n\n**SEBEP:** `{v_error}`\n\nSadece ses gönderiliyor."
                bot.edit_message_text(hata_mesaji, message.chat.id, msg.message_id, parse_mode="Markdown")
                
                with open(audio_filename, "rb") as audio:
                    bot.send_audio(message.chat.id, audio, caption=caption_text, title=content['title'], timeout=120)

            try:
                bot.delete_message(message.chat.id, msg.message_id)
            except: pass 
            
            if os.path.exists(audio_filename): os.remove(audio_filename)
            
        else:
            bot.edit_message_text("❌ Ses üretilemedi.", message.chat.id, msg.message_id)
            
    except Exception as e:
        bot.reply_to(message, f"Kritik Hata: {e}")

if __name__ == "__main__":
    print("Bot başlatılıyor... ⚡ ON-THE-FLY STREAM (SIFIR İNDİRME) MOTORU AKTİF!", flush=True)
    bot.polling(non_stop=True)

