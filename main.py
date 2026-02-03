import os
import telebot
import requests
import random
import subprocess
import numpy as np
import textwrap
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

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

# --- 1. SENARYO ---
def get_script(topic):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        f"Write a viral and terrifying horror story about '{topic}' for a YouTube Short. "
        "Use short, punchy sentences. Add suspense every 2-3 sentences. "
        "Start with a shocking hook. Length 110-125 words. No intro or outro. Simple English."
    )
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        pass

    return "When I looked in the mirror, it was not me anymore. Something else was smiling back at me. I tried to scream, but nothing came out."

def make_hook_script(script):
    sentences = script.replace("!", ".").replace("?", ".").split(".")
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) < 3:
        return script
    hook = sentences[-1]
    rest = ". ".join(sentences[:-1])
    return f"{hook}. {rest}."

# --- 2. VİDEO İNDİRME ---
def get_multiple_videos(total_duration):
    headers = {"Authorization": PEXELS_API_KEY}

    queries = [
        "dark room",
        "creepy mirror",
        "empty hallway night",
        "shadow corridor",
        "abandoned room",
        "dark bathroom mirror"
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

# --- 3. ALTYAZI ---
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

# --- 4. MONTAJ ---
def build_video(script):
    try:
        generate_tts(script, "voice.mp3")
        audio = AudioFileClip("voice.mp3")

        paths = get_multiple_videos(audio.duration)
        if not paths:
            return "Görüntü bulunamadı."

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

        if main_video.duration < audio.duration:
            main_video = main_video.loop(duration=audio.duration)
        else:
            main_video = main_video.subclip(0, audio.duration)

        main_video = main_video.set_audio(audio)

        subs = create_subtitles(script, main_video.duration, main_video.size)
        final_result = CompositeVideoClip([main_video, subs])

        final_result.write_videofile(
            "final_video.mp4",
            codec="libx264",
            audio_codec="aac",
            fps=30,
            preset="medium",
            bitrate="4000k",
            ffmpeg_params=["-pix_fmt", "yuv420p"],
            threads=4
        )

        for c in video_clips:
            c.close()
        audio.close()

        return "final_video.mp4"

    except Exception as e:
        return f"Hata: {str(e)}"

# --- 5. DİNAMİK YOUTUBE AÇIKLAMA (HİKÂYEYE DAYALI, İNGİLİZCE) ---
def generate_story_based_description(script, topic):
    """
    Videodaki hikâyeye uygun, İngilizce açıklama ve hashtagler üretir.
    """
    # Hikâyeden rastgele bir cümle seçerek hook yap
    sentences = [s.strip() for s in script.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    hook = sentences[0] if sentences else f"A terrifying {topic} story you must watch!"

    calls_to_action = [
        "Like, comment, and subscribe for more! 🔔",
        "Don't forget to like and share this scary story! 👻",
        "Enjoyed it? Hit like and subscribe for more! 🎬"
    ]

    hashtags = [
        f"#{topic.replace(' ', '')}",
        "#horror",
        "#scary",
        "#shorts",
        "#creepy",
        "#viral",
        "#thriller",
        "#mystery"
    ]

    import random
    cta = random.choice(calls_to_action)
    hashtags_text = " ".join(hashtags)

    return f"{hook}\n\n{cta}\n\n{hashtags_text}"

# --- TELEGRAM ---
@bot.message_handler(commands=['video'])
def handle_video(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Please provide a topic.")
        return

    topic = args[1]
    bot.reply_to(message, f"🎥 Processing '{topic}'...")

    script = get_script(topic)
    script = make_hook_script(script)

    video_path = build_video(script)

    if "final_video" in video_path:
        description = generate_story_based_description(script, topic)
        with open(video_path, 'rb') as v:
            bot.send_video(
                message.chat.id,
                v,
                caption=f"🎬 Topic: {topic}\n\nDescription:\n{description}"
            )
    else:
        bot.reply_to(message, video_path)

# Daha stabil polling
while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=60)
    except Exception as e:
        print("Polling error, restarting:", e)
