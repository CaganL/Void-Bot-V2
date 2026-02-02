import os
import random
import json
import sys
import asyncio
import edge_tts
import textwrap
import requests
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, vfx, CompositeAudioClip
from moviepy.audio.fx.all import volumex

# --- GLOBAL ENGLISH CONTENT POOL ---
STORIES = [
    {
        "topic": "HORROR", 
        "search_query": "scary forest fog dark spooky", 
        "title": "😱 MIDNIGHT VISITOR", 
        "text": "According to the Japanese legend of Kuchisake-onna, if you walk on a foggy street at night and a masked woman asks, 'Am I beautiful?', never answer. If you say yes, she removes her mask to reveal a slit mouth and screams, 'How about now?' If you say no... well, you don't want to know."
    },
    {
        "topic": "FACTS", 
        "search_query": "space galaxy cinematic stars", 
        "title": "🪐 VENUS IS WEIRD", 
        "text": "Time on Venus is absolute chaos. Venus rotates so slowly that a single day on Venus lasts longer than a whole year on Venus. Imagine celebrating your birthday every single day. That is the hottest planet in our solar system for you."
    },
    {
        "topic": "OCEAN", 
        "search_query": "deep ocean waves cinematic", 
        "title": "🌊 POWER OF THE OCEAN", 
        "text": "The oceans are so massive that humans have explored only five percent of them. If every single human on Earth jumped into the ocean at the same time, the water level would rise by less than the width of a human hair. We are nothing compared to the deep blue."
    },
    {
        "topic": "SCIENCE", 
        "search_query": "science dna laboratory abstract", 
        "title": "🍌 YOU ARE A BANANA", 
        "text": "Do you feel special? Think again. Human DNA is fifty percent identical to the DNA of a banana. Genetically speaking, you are half a fruit. Nature really has a twisted sense of humor, doesn't it?"
    }
]

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

def get_credentials():
    token_json = os.environ.get("TOKEN_JSON")
    if not token_json:
        print("🚨 ERROR: TOKEN_JSON not found!")
        sys.exit(1)
    return Credentials.from_authorized_user_info(json.loads(token_json))

async def generate_pro_voice(text, filename="voice.mp3"):
    print("🎙️ Generating English Voiceover...")
    try:
        # Changed to English Voice (Christopher is deep and cinematic)
        communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="+5%", pitch="-2Hz")
        await communicate.save(filename)
        print("✅ Voiceover ready.")
    except Exception as e:
        print(f"🚨 VOICE ERROR: {e}")
        sys.exit(1)

def download_video_from_pexels(query):
    if not PEXELS_API_KEY:
        print("🚨 ERROR: PEXELS_API_KEY not found!")
        sys.exit(1)
    
    print(f"🌍 Searching Pexels for: {query}")
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=5"
    
    try:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            print(f"🚨 PEXELS API ERROR: {r.status_code}")
            sys.exit(1)
            
        data = r.json()
        if "videos" in data and len(data["videos"]) > 0:
            video_data = random.choice(data["videos"])
            best_link = video_data["video_files"][0]["link"]
            print(f"📥 Downloading video... (ID: {video_data['id']})")
            
            vid_r = requests.get(best_link, stream=True)
            with open("downloaded_bg.mp4", "wb") as f:
                for chunk in vid_r.iter_content(chunk_size=1024*1024): f.write(chunk)
            
            if os.path.getsize("downloaded_bg.mp4") < 1000:
                print("🚨 ERROR: Downloaded file is empty!")
                sys.exit(1)
                
            return "downloaded_bg.mp4"
        else:
            print("🚨 ERROR: No videos found for this topic!")
            sys.exit(1)
    except Exception as e:
        print(f"🚨 DOWNLOAD ERROR: {e}")
        sys.exit(1)

def main():
    story_data = random.choice(STORIES)
    print(f"🎬 PROCESSING: {story_data['title']}")
    
    # 1. Voice
    asyncio.run(generate_pro_voice(story_data['text']))
    voice_audio = AudioFileClip("voice.mp3")
    
    # 2. Video Download
    video_path = download_video_from_pexels(story_data["search_query"])
    
    print("🎞️ Editing Video (MoviePy)...")
    background = VideoFileClip(video_path)
    
    if background.w > background.h:
        background = background.crop(x_center=background.w/2, width=background.h*9/16, height=background.h)
    background = background.resize(height=1920).crop(x_center=background.w/2, width=1080, height=1920)
    background = background.fx(vfx.loop, duration=voice_audio.duration + 2)
    
    video = background.set_duration(voice_audio.duration + 1.5).set_audio(voice_audio)
    
    # English Titles
    title_clip = TextClip(story_data['title'], fontsize=70, color='white', bg_color='#cc0000', 
                          size=(900, None), method='caption', align='center')
    title_clip = title_clip.set_pos(('center', 150)).set_duration(video.duration)
    
    output_file = "shorts_video.mp4"
    print("⚙️ Rendering...")
    final_video = CompositeVideoClip([video, title_clip])
    final_video.write_videofile(output_file, fps=24, bitrate="5000k", codec="libx264", audio_codec="aac")
    
    time.sleep(5)
    
    if not os.path.exists(output_file):
        print("🚨 ERROR: Render failed, file not found!")
        sys.exit(1)
        
    print(f"✅ Video created successfully!")
    
    # 3. Upload to YouTube (English Metadata)
    print("🚀 Uploading to YouTube...")
    try:
        creds = get_credentials()
        youtube = build('youtube', 'v3', credentials=creds)
        
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": f"{story_data['title']} #shorts",
                    "description": f"{story_data['text']}\n\nSubscribe for more mysteries: @GolgeArsiviTR\n\n#shorts #horror #facts #mystery #{story_data['topic'].lower()}",
                    "categoryId": "27" # Education
                },
                "status": {
                    "privacyStatus": "public", 
                    "selfDeclaredMadeForKids": False
                }
            },
            media_body=MediaFileUpload(output_file)
        )
        response = request.execute()
        print(f"🎉 SUCCESS! Video ID: {response['id']}")
        print(f"🔗 Link: https://youtube.com/shorts/{response['id']}")
        
    except Exception as e:
        print(f"🚨 UPLOAD ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
