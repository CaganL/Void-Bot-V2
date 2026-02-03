import os
import telebot
import requests
import random
import subprocess
import numpy as np
import textwrap
import time
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, afx

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BACKGROUND_MUSIC = "background.mp3"  # Trend veya ücretsiz arka plan müziği

bot = telebot.TeleBot(TELEGRAM_TOKEN)

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

# --- FONT ---
def download_font():
    font_path = "Oswald-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald-Bold.ttf"
        try:
            r = requests.get(url, timeout=10)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except:
            pass
    return font_path

# --- TTS ---
def generate_tts(text, output="voice.mp3"):
    cmd = [
        "edge-tts",
        "--voice", "en-US-ChristopherNeural",
        "--text", text,
        "--write-media", output
    ]
    subprocess.run(cmd, check=True)

# --- SENARYO ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        f"Write a viral and engaging story about '{topic}' for a YouTube Short. "
        "Use short, punchy sentences. Add suspense every 2-3 sentences. "
        "Start with a shocking or motivating hook. Length 110-125 words. No intro or outro. Simple English."
    )
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        pass
    return f"A {topic} story that will grab attention immediately!"

def make_hook_script(script):
    sentences = script.replace("!", ".").replace("?", ".").split(".")
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) < 3:
        return script
    hook = sentences[-1]
    rest = ". ".join(sentences[:-1])
    return f"{hook}. {rest}."

# --- VIDEO İNDİRME ---
def get_multiple_videos(total_duration):
    headers = {"Authorization": PEXELS_API_KEY}
    queries = [
        "dark room", "creepy mirror", "empty hallway night",
        "shadow corridor", "abandoned room", "dark bathroom mirror"
    ]
    paths = []
    current_dur = 0
    i = 0
    random.shuffle(queries)
    try:
        for q in queries:
            if current_dur >= total_duration:
                break
            search_url = f"https://api.pexels.com/videos/search?query={q}&per_page=8&orientation=portrait"
            r = requests.get(search_url, headers=headers, timeout=15)
            videos_data = r.json().get("videos", [])
            if not videos_data:
                continue
            v = random.choice(videos_data)
            link = max(v["video_files"], key=lambda x: x["height"])["link"]
            path = f"part_{i}.mp4"
            i += 1
            with open(path, "wb") as f:
                f.write(requests.get(link, timeout=20).content)
            clip = VideoFileClip(path)
            paths.append(path)
            current_dur += clip.duration
            clip.close()
        return paths if paths else None
    except:
        return None

# --- ALTYAZI ---
def split_for_subtitles(text):
    words = text.split()
    chunks = []
    current = []
    for w in words:
        current.append(w)
        if len(current) >= 4:
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks

def create_subtitles(text, total_duration, video_size):
    W, H = video_size
    font_path = download_font()
    fontsize = int(W / 9)
    try:
        font = ImageFont.truetype(font_path, fontsize)
    except:
        font = ImageFont.load_default()
    chunks = split_for_subtitles(text)
    duration_per_chunk = total_duration / len(chunks)
    clips = []
    for chunk in chunks:
        img = Image.new('RGBA', (int(W), int(H)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        wrapper = textwrap.TextWrapper(width=16)
        caption_wrapped = '\n'.join(wrapper.wrap(text=chunk.upper()))
        bbox = draw.textbbox((0, 0), caption_wrapped, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        box_padding = 20
        box_x1 = (W - tw) / 2 - box_padding
        box_y1 = H * 0.75 - box_padding
        box_x2 = (W + tw) / 2 + box_padding
        box_y2 = H * 0.75 + th + box_padding
        draw.rectangle([box_x1, box_y1, box_x2, box_y2], fill=(0, 0, 0, 160))
        draw.text(
            ((W - tw) / 2, H * 0.75),
            caption_wrapped,
            font=font,
            fill="#FFFFFF",
            align="center",
            stroke_width=3,
            stroke_fill="black"
        )
        clips.append(ImageClip(np.array(img)).set_duration(duration_per_chunk))
    return concatenate_videoclips(clips)

# --- MONTAJ ---
def build_video(script, mode="final"):
    try:
        generate_tts(script, "voice.mp3")
        audio = AudioFileClip("voice.mp3")
        paths = get_multiple_videos(audio.duration)
        if not paths:
            return "No video clips found."
        video_clips = []
        for p in paths:
            c = VideoFileClip(p)
            new_h = 1080
            new_w = int((new_h * (c.w / c.h)) // 2) * 2
            c = c.resize(height=new_h, width=new_w)
            target_w = int((new_h * (9 / 16)) // 2) * 2
            if c.w > target_w:
                c = c.crop(x1=(c.w / 2 - target_w / 2), width=target_w, height=new_h)
            video_clips.append(c)
        main_video = concatenate_videoclips(video_clips, method="compose")
        # --- Shorts uyumlu sürede kes ---
        if main_video.duration > 45:
            main_video = main_video.subclip(0, 45)
        elif main_video.duration < 30:
            main_video = main_video.loop(duration=30)
        # --- Arka plan müziği ekle ---
        if os.path.exists(BACKGROUND_MUSIC):
            music = AudioFileClip(BACKGROUND_MUSIC).subclip(0, main_video.duration).volumex(0.3)
            main_video = main_video.set_audio(audio.audio_fadeout(0.5).fx(afx.audio_loop, duration=main_video.duration).volumex(1.0).fx(afx.audio_mix, music))
        else:
            main_video = main_video.set_audio(audio)
        # --- Altyazı ---
        subs = create_subtitles(script, main_video.duration, main_video.size)
        final_result = CompositeVideoClip([main_video, subs])
        # --- MODE OPTIMIZASYONU ---
        if mode == "test":
            fps = 24
            preset = "fast"
            bitrate = "2000k"
        else:  # final
            fps = 30
            preset = "medium"
            bitrate = "4000k"
        final_result.write_videofile(
            "final_video.mp4",
            codec="libx264",
            audio_codec="aac",
            fps=fps,
            preset=preset,
            bitrate=bitrate,
            ffmpeg_params=["-pix_fmt", "yuv420p"],
            threads=2
        )
        # --- Thumbnail oluştur ---
        frame = final_result.get_frame(1)
        Image.fromarray(frame).save("thumbnail.jpg")
        for c in video_clips:
            c.close()
        audio.close()
        return "final_video.mp4"
    except Exception as e:
        return f"Error: {str(e)}"

# --- DİNAMİK AÇIKLAMA (KONUYA GÖRE HOOK & HASHTAG) ---
def generate_story_based_description(script, topic):
    sentences = [s.strip() for s in script.replace("!", ".").replace("?", ".").split(".") if s.strip()]

    # --- Hook seçimi ---
    if topic.lower() in ["horror", "scary", "creepy", "thriller"]:
        hook = sentences[0] if sentences else f"A terrifying {topic} story you must watch!"
    elif topic.lower() in ["motivation", "success", "inspiration", "selfhelp"]:
        hook = sentences[0] if sentences else f"Push yourself, because greatness doesn’t wait!"
    else:
        hook = sentences[0] if sentences else f"Watch this amazing {topic} story!"

    # --- Call-to-action ---
    calls_to_action = [
        "Like, comment, and subscribe for more! 🔔",
        "Don't forget to like and share! 👀",
        "Enjoyed it? Hit like and subscribe! 🎬"
    ]

    # --- Hashtaglar ---
    if topic.lower() in ["horror", "scary", "creepy", "thriller"]:
        hashtags = [f"#{topic.replace(' ', '')}", "#horror", "#scary", "#shorts", "#creepy", "#viral", "#thriller"]
    elif topic.lower() in ["motivation", "success", "inspiration", "selfhelp"]:
        hashtags = [f"#{topic.replace(' ', '')}", "#motivation", "#success", "#shorts", "#inspiration", "#viral"]
    else:
        hashtags = [f"#{topic.replace(' ', '')}", "#shorts", "#viral"]

    import random
    cta = random.choice(calls_to_action)
    hashtags_text = " ".join(hashtags)

    return f"{hook}\n\n{cta}\n\n{hashtags_text}"

# --- TELEGRAM ---
@bot.message_handler(commands=['video'])
def handle_video(message):
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        bot.reply_to(message, "Please provide a topic.")
        return
    topic = args[1]
    mode = "test" if len(args) > 2 and args[2].lower() == "test" else "final"
    bot.reply_to(message, f"🎥 Processing '{topic}' in {mode} mode...")
    script = get_script(topic)
    script = make_hook_script(script)
    video_path = build_video(script, mode=mode)
    if "final_video" in video_path:
        description = generate_story_based_description(script, topic)
        time.sleep(2)
        with open(video_path, 'rb') as v:
            bot.send_video(
                message.chat.id,
                v,
                caption=f"🎬 Topic: {topic}\n\nDescription:\n{description}",
                thumb=open("thumbnail.jpg", "rb")
            )
    else:
        bot.reply_to(message, video_path)

# --- STABIL POLLING ---
while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=60)
    except Exception as e:
        print("Polling error, restarting:", e)
