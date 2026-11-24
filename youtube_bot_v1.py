"""
╔══════════════════════════════════════════════════════════════╗
║         YOUTUBE AUTOMATION BOT — ALL IN ONE FILE             ║
║         Channels: Past Shock + Soul Flare                    ║
║         By: Destiny Growrich                                 ║
╚══════════════════════════════════════════════════════════════╝

Pipeline per channel:
  Trends → Score → Script → Hook → Voice → Images → Video → Upload → Telegram

Install dependencies first:
  pip install google-api-python-client google-auth google-auth-oauthlib
              edge-tts gTTS pytrends schedule pytz requests Pillow

Also requires FFmpeg installed on the system:
  Ubuntu/Oracle Cloud: sudo apt install -y ffmpeg
"""

# ══════════════════════════════════════════════════════════════
#  IMPORTS
# ══════════════════════════════════════════════════════════════
import os, sys, json, time, pickle, logging, asyncio, re, math
import subprocess, tempfile, shutil, base64, urllib.parse
from datetime import datetime
from pathlib import Path

import requests
import schedule
import pytz

# ══════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════

# ── API Keys ─────────────────────────────────────────────────
GEMINI_API_KEY     = "AIzaSyBWCdATH1xi7RIBcBnf4MAzUakcc604uiQ"
GROQ_API_KEY       = "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"
TELEGRAM_BOT_TOKEN = "8761177135:AAHxzhJ3czzoHLaFArl0CTq9RwI6bWk_3Qs"
TELEGRAM_CHAT_ID   = "-1003656979711"

# ── YouTube Auth ──────────────────────────────────────────────
YOUTUBE_CLIENT_SECRETS = "client_secrets.json"
YOUTUBE_TOKEN_FILE     = "token.json"
YOUTUBE_SCOPES         = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

# ── Image Generation ──────────────────────────────────────────
CLOUDFLARE_ACCOUNT_ID = ""      # Fill in when ready
CLOUDFLARE_API_TOKEN  = ""      # Fill in when ready
AI_HORDE_API_KEY      = "0000000000"  # Anonymous - works without signup

# ── Video Settings ────────────────────────────────────────────
VIDEO_FPS             = 30
ZOOM_SPEED            = 0.0005
SUBTITLE_FONT_SIZE    = 48
IMAGE_WIDTH           = 576
IMAGE_HEIGHT          = 1024   # 9:16 vertical

# ── Channel Profiles ──────────────────────────────────────────
CHANNELS = {
    "past_shock": {
        "name": "Past Shock",
        "youtube_channel_id": "",          # Add your Past Shock channel ID
        "niche": "dark history",
        "style": "cinematic, dramatic, dark, historically accurate",
        "tone": "shocking, intense, educational, gripping",
        "duration_seconds": 58,
        "videos_per_day": 4,
        "posting_times": ["08:00", "12:00", "17:00", "20:00"],
        "timezone": "Africa/Lagos",
        "voice": "en-US-GuyNeural",
        "image_style": "cinematic dark historical photography, dramatic lighting, ultra realistic, vertical portrait 9:16",
        "output_dir": "output/past_shock",
        "seo": {
            "category_id": "27",
            "default_tags": ["history","shocking history","dark history","pastshock",
                             "historyfacts","shorts","historytok","didyouknow","darkhistory"]
        }
    },
    "soul_flare": {
        "name": "Soul Flare",
        "youtube_channel_id": "",          # Add your Soul Flare channel ID
        "niche": "animated horror",
        "style": "2D animated, scary, atmospheric, dark fantasy",
        "tone": "terrifying, mysterious, suspenseful, haunting",
        "duration_seconds": 58,
        "videos_per_day": 2,
        "posting_times": ["19:00", "22:00"],
        "timezone": "Africa/Lagos",
        "voice": "en-US-ChristopherNeural",
        "image_style": "2D animated horror illustration, dark fantasy art, scary atmosphere, vibrant colors, vertical portrait 9:16",
        "output_dir": "output/soul_flare",
        "seo": {
            "category_id": "1",
            "default_tags": ["horror","animation","scary","soulflare","horrortok",
                             "animatedhorror","shorts","scarystories","horrorfan","darkanimation"]
        }
    }
}

# ── Logging ───────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("YTBot")


# ══════════════════════════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════════════════════════

def tg(text: str):
    """Send Telegram message."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        log.error(f"Telegram error: {e}")

def tg_start(channel):   tg(f"🚀 <b>Pipeline Started</b> — {channel}")
def tg_done(channel):    tg(f"🏁 <b>Pipeline Complete</b> — {channel}")
def tg_created(channel, title): tg(f"🎬 <b>Video Created</b>\n📺 {channel}\n📝 {title}")
def tg_uploaded(channel, title, url): tg(f"✅ <b>Uploaded!</b>\n📺 {channel}\n📝 {title}\n🔗 {url}")
def tg_error(channel, stage, err): tg(f"❌ <b>Error</b> — {channel}\n⚙️ {stage}\n💬 {err}")
def tg_summary(channel, made, uploaded): tg(f"📊 <b>Daily Summary — {channel}</b>\n🎬 Created: {made}\n📤 Uploaded: {uploaded}")


# ══════════════════════════════════════════════════════════════
#  AI CALLER (Gemini → Groq fallback)
# ══════════════════════════════════════════════════════════════

def call_gemini(prompt: str) -> str:
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}")
    r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def call_groq(prompt: str) -> str:
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 2000, "temperature": 0.85},
        timeout=30
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def call_ai(prompt: str) -> str:
    """Call Gemini first, fall back to Groq."""
    try:
        log.info("Calling Gemini...")
        return call_gemini(prompt)
    except Exception as e:
        log.warning(f"Gemini failed ({e}) — trying Groq...")
        return call_groq(prompt)


def parse_json_response(raw: str) -> dict:
    """Safely parse JSON from AI response."""
    clean = raw.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(clean)


# ══════════════════════════════════════════════════════════════
#  TREND DETECTION
# ══════════════════════════════════════════════════════════════

_trend_cache = {"data": [], "ts": 0}

NICHE_KEYWORDS = {
    "dark history":    ["war","battle","massacre","disaster","death","history",
                        "ancient","empire","mystery","shocking"],
    "animated horror": ["horror","scary","ghost","monster","haunted","demon",
                        "cursed","paranormal","dark","evil"]
}

FALLBACK_TOPICS = {
    "dark history": [
        "The Most Brutal Execution in History",
        "Ancient Civilizations That Vanished Overnight",
        "The Darkest Secret of World War II",
        "Forgotten Massacres That Changed History",
        "The Most Feared Ruler in Ancient Times",
        "The Plague That Wiped Out Half of Europe"
    ],
    "animated horror": [
        "The Creature That Haunts the Forest",
        "A Shadow That Should Not Exist",
        "The Last Person to Enter That House",
        "Something Is Watching From the Dark",
        "The Night the Town Disappeared",
        "The Entity That Follows You Home"
    ]
}


def get_trends(channel_key: str) -> list:
    """Fetch trending topics. Returns combined Google Trends + fallbacks."""
    channel = CHANNELS[channel_key]
    niche   = channel["niche"]
    now     = time.time()

    # Use cache if fresh
    if now - _trend_cache["ts"] < 3600 and _trend_cache["data"]:
        return _trend_cache["data"]

    topics = []

    # Google Trends via pytrends
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25), retries=2, backoff_factor=0.5)
        df = pt.trending_searches(pn="united_states")
        trending = df[0].tolist()[:20]
        keywords = NICHE_KEYWORDS.get(niche, [])
        filtered = [t for t in trending if any(k in t.lower() for k in keywords)]
        topics.extend(filtered)
        log.info(f"Google Trends: {len(filtered)} matched topics")
    except Exception as e:
        log.warning(f"Google Trends error: {e}")

    # Always add fallbacks so we never run empty
    topics.extend(FALLBACK_TOPICS.get(niche, []))
    result = list(dict.fromkeys(topics))[:15]  # deduplicate

    _trend_cache["data"] = result
    _trend_cache["ts"]   = now
    return result


# ══════════════════════════════════════════════════════════════
#  TOPIC SCORING
# ══════════════════════════════════════════════════════════════

EMOTION_WORDS = ["shocking","brutal","secret","forbidden","terrifying","horrifying",
                 "dark","evil","cursed","haunted","massacre","betrayal","truth",
                 "hidden","vanished","mystery","deadly","nightmare","feared","exposed"]

HOOK_WORDS    = ["why","how","what happened","nobody talks about","untold",
                 "you won't believe","the real reason","the truth about",
                 "the last","the first","most","never before","secret","revealed"]

COMP_PHRASES  = ["world war","titanic","hitler","abraham lincoln","napoleon",
                 "julius caesar","cleopatra","great wall"]


def score_topic(topic: str, position: int = 5) -> dict:
    t = topic.lower()
    trend_score = max(0, 100 - position * 8)
    emotion     = min(100, sum(1 for w in EMOTION_WORDS if w in t) * 25)
    hook        = min(100, sum(1 for w in HOOK_WORDS    if w in t) * 30)
    competition = max(0,  100 - sum(1 for p in COMP_PHRASES if p in t) * 40)
    final       = trend_score*0.35 + emotion*0.25 + hook*0.25 + competition*0.15
    return {"topic": topic, "score": round(final, 1)}


def select_top_topics(topics: list, channel_key: str) -> list:
    n      = CHANNELS[channel_key]["videos_per_day"]
    scored = [score_topic(t, i+1) for i, t in enumerate(topics)]
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:n]
    for t in top:
        log.info(f"  ✅ [{t['score']}] {t['topic']}")
    return top


# ══════════════════════════════════════════════════════════════
#  SCRIPT + SEO GENERATOR
# ══════════════════════════════════════════════════════════════

def generate_hooks(topic: str, channel_key: str) -> dict:
    ch = CHANNELS[channel_key]
    prompt = f"""
You are a YouTube Shorts expert for "{ch['name']}" — {ch['niche']} channel.
Tone: {ch['tone']}
Topic: "{topic}"

Generate 4 hooks: shock, curiosity, emotional, mystery.
Evaluate each against 4 viewer types (curious, emotional, skeptical, scroll_addict) score 1-10.

Return ONLY valid JSON:
{{
  "hooks": {{"shock":"...","curiosity":"...","emotional":"...","mystery":"..."}},
  "best_hook": "shock|curiosity|emotional|mystery",
  "best_hook_text": "..."
}}"""
    try:
        return parse_json_response(call_ai(prompt))
    except Exception as e:
        log.error(f"Hook error: {e}")
        return {"best_hook": "shock", "best_hook_text": f"You won't believe what happened: {topic}"}


def generate_script(topic: str, hook: str, channel_key: str) -> dict | None:
    ch = CHANNELS[channel_key]
    prompt = f"""
You are writing a YouTube Shorts script for "{ch['name']}" — {ch['niche']}.
Style: {ch['style']} | Tone: {ch['tone']} | Duration: {ch['duration_seconds']}s (~140 words)
Topic: "{topic}"
Opening Hook: "{hook}"

Write exactly 10 scenes. Each scene = 1 image + 1-2 sentences narration (~5 seconds).

Return ONLY valid JSON:
{{
  "scenes": [
    {{
      "scene_number": 1,
      "narration": "spoken words here",
      "image_prompt": "detailed image prompt, {ch['image_style']}, dramatic lighting, high quality"
    }}
  ],
  "full_narration": "complete script as one paragraph"
}}"""
    try:
        return parse_json_response(call_ai(prompt))
    except Exception as e:
        log.error(f"Script error: {e}")
        return None


def generate_seo(topic: str, narration: str, channel_key: str) -> dict:
    ch       = CHANNELS[channel_key]
    def_tags = ch["seo"]["default_tags"]
    prompt   = f"""
You are a YouTube SEO expert for the {ch['niche']} niche.
Channel: "{ch['name']}"
Topic: "{topic}"
Script: "{narration[:300]}"

Return ONLY valid JSON:
{{
  "title": "SEO title under 70 chars with power words",
  "description": "300-500 word description with keywords and call to action",
  "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10"],
  "hashtags": "#tag1 #tag2 #tag3 #tag4 #tag5 #tag6 #tag7 #tag8 #tag9 #tag10"
}}"""
    try:
        data     = parse_json_response(call_ai(prompt))
        all_tags = list(set(data.get("tags", []) + def_tags))
        data["tags"] = all_tags[:30]
        return data
    except Exception as e:
        log.error(f"SEO error: {e}")
        return {
            "title": topic,
            "description": f"{topic} #shorts",
            "tags": def_tags,
            "hashtags": " ".join(f"#{t}" for t in def_tags)
        }


# ══════════════════════════════════════════════════════════════
#  TEXT-TO-SPEECH (Edge TTS → gTTS)
# ══════════════════════════════════════════════════════════════

def optimize_speech(text: str) -> str:
    text = re.sub(r'\. ', '.  ', text)
    text = re.sub(r', ',  ',  ', text)
    text = re.sub(r'(\d{4})', r' \1 ', text)
    return re.sub(r'  +', '  ', text).strip()


async def _edge_tts_async(text: str, voice: str, path: str):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate="-5%", pitch="-10Hz").save(path)


def generate_voiceover(text: str, channel_key: str, output_path: str) -> bool:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    voice     = CHANNELS[channel_key]["voice"]
    optimized = optimize_speech(text)

    # Edge TTS (primary)
    try:
        import edge_tts
        asyncio.run(_edge_tts_async(optimized, voice, output_path))
        log.info(f"Edge TTS ✅ {output_path}")
        return True
    except Exception as e:
        log.warning(f"Edge TTS failed: {e} — trying gTTS...")

    # gTTS (fallback)
    try:
        from gtts import gTTS
        gTTS(text=optimized, lang="en", slow=False).save(output_path)
        log.info(f"gTTS ✅ {output_path}")
        return True
    except Exception as e:
        log.error(f"gTTS failed: {e}")
        return False


def get_audio_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True
        )
        return float(r.stdout.strip())
    except:
        return 58.0


# ══════════════════════════════════════════════════════════════
#  IMAGE GENERATION (Cloudflare → AI Horde → Pollinations)
# ══════════════════════════════════════════════════════════════

def gen_cloudflare(prompt: str, path: str) -> bool:
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        return False
    try:
        url = (f"https://api.cloudflare.com/client/v4/accounts/"
               f"{CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell")
        r = requests.post(url,
            headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
            json={"prompt": prompt, "num_steps": 8,
                  "width": IMAGE_WIDTH, "height": IMAGE_HEIGHT},
            timeout=60)
        r.raise_for_status()
        open(path, "wb").write(r.content)
        return True
    except Exception as e:
        log.error(f"Cloudflare: {e}")
        return False


def gen_ai_horde(prompt: str, path: str) -> bool:
    try:
        headers = {"apikey": AI_HORDE_API_KEY, "Content-Type": "application/json"}
        r = requests.post("https://stablehorde.net/api/v2/generate/async",
            headers=headers,
            json={"prompt": prompt,
                  "params": {"width": IMAGE_WIDTH, "height": IMAGE_HEIGHT,
                             "steps": 20, "n": 1},
                  "models": ["Deliberate"], "nsfw": False},
            timeout=30)
        r.raise_for_status()
        job_id = r.json()["id"]

        for _ in range(36):   # max 3 minutes
            time.sleep(5)
            check = requests.get(f"https://stablehorde.net/api/v2/generate/check/{job_id}",
                                 headers=headers, timeout=10).json()
            if check.get("done"):
                result  = requests.get(f"https://stablehorde.net/api/v2/generate/status/{job_id}",
                                       headers=headers, timeout=10).json()
                img_b64 = result["generations"][0]["img"]
                open(path, "wb").write(base64.b64decode(img_b64))
                log.info(f"AI Horde ✅ {path}")
                return True
        return False
    except Exception as e:
        log.error(f"AI Horde: {e}")
        return False


def gen_pollinations(prompt: str, path: str) -> bool:
    try:
        url = (f"https://image.pollinations.ai/prompt/"
               f"{urllib.parse.quote(prompt)}"
               f"?width={IMAGE_WIDTH}&height={IMAGE_HEIGHT}&nologo=true")
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        open(path, "wb").write(r.content)
        log.info(f"Pollinations ✅ {path}")
        return True
    except Exception as e:
        log.error(f"Pollinations: {e}")
        return False


def generate_image(prompt: str, path: str) -> bool:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    for fn, name in [(gen_cloudflare,"Cloudflare"),(gen_ai_horde,"AI Horde"),(gen_pollinations,"Pollinations")]:
        if fn(prompt, path) and os.path.exists(path) and os.path.getsize(path) > 10_000:
            log.info(f"Image OK from {name}")
            return True
        if os.path.exists(path):
            os.remove(path)
    return False


def generate_all_images(scenes: list, output_dir: str) -> list:
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for i, scene in enumerate(scenes):
        prompt = scene.get("image_prompt", f"cinematic dramatic scene {i+1}")
        path   = os.path.join(output_dir, f"scene_{i+1:02d}.jpg")
        log.info(f"Image {i+1}/{len(scenes)}...")
        if generate_image(prompt, path):
            paths.append(path)
        time.sleep(1)
    log.info(f"Images: {len(paths)}/{len(scenes)}")
    return paths


# ══════════════════════════════════════════════════════════════
#  VIDEO ASSEMBLY (FFmpeg — Ken Burns + Subtitles)
# ══════════════════════════════════════════════════════════════

def ffmpeg(cmd: list, label="") -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            log.error(f"FFmpeg [{label}]:\n{r.stderr[-400:]}")
            return False
        return True
    except Exception as e:
        log.error(f"FFmpeg [{label}]: {e}")
        return False


def ken_burns(img: str, out: str, duration: float, direction: str) -> bool:
    w, h, fps = 1080, 1920, VIDEO_FPS
    frames    = int(duration * fps)
    zs        = ZOOM_SPEED
    effects   = {
        "zoom_in":   f"scale=8000:-1,zoompan=z='min(zoom+{zs},1.5)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}",
        "zoom_out":  f"scale=8000:-1,zoompan=z='if(lte(zoom,1.0),1.5,max(1.001,zoom-{zs}))':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}",
        "pan_left":  f"scale=8000:-1,zoompan=z=1.3:d={frames}:x='if(lte(on,1),0,x+1)':y='ih/2-(ih/zoom/2)':s={w}x{h}",
        "pan_right": f"scale=8000:-1,zoompan=z=1.3:d={frames}:x='if(gte(x+iw/zoom,iw),iw-iw/zoom,x+1)':y='ih/2-(ih/zoom/2)':s={w}x{h}",
    }
    return ffmpeg([
        "ffmpeg","-y","-loop","1","-i",img,
        "-vf", effects.get(direction, effects["zoom_in"]),
        "-t", str(duration), "-r", str(fps),
        "-c:v","libx264","-pix_fmt","yuv420p","-preset","fast", out
    ], f"kb_{direction}")


def make_srt(scenes: list, audio_dur: float, path: str):
    dur = audio_dur / len(scenes)
    def ft(s):
        h,m,sc,ms = int(s//3600),int((s%3600)//60),int(s%60),int((s%1)*1000)
        return f"{h:02d}:{m:02d}:{sc:02d},{ms:03d}"
    with open(path,"w",encoding="utf-8") as f:
        for i, scene in enumerate(scenes):
            text  = scene.get("narration","").strip()
            words = text.split()
            if len(words) > 10:
                mid  = len(words)//2
                text = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
            f.write(f"{i+1}\n{ft(i*dur)} --> {ft((i+1)*dur)}\n{text}\n\n")


def assemble_video(images: list, scenes: list, audio: str, output: str) -> bool:
    if not images:
        return False
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    audio_dur  = get_audio_duration(audio)
    scene_dur  = audio_dur / len(images)
    directions = ["zoom_in","zoom_out","pan_left","pan_right"]

    with tempfile.TemporaryDirectory() as tmp:
        # 1. Ken Burns each image
        clips = []
        for i, img in enumerate(images):
            clip = os.path.join(tmp, f"clip_{i:02d}.mp4")
            if ken_burns(img, clip, scene_dur, directions[i % 4]):
                clips.append(clip)
            else:
                # Static fallback
                if ffmpeg(["ffmpeg","-y","-loop","1","-i",img,
                           "-t",str(scene_dur),
                           "-vf","scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                           "-r",str(VIDEO_FPS),"-c:v","libx264","-pix_fmt","yuv420p",clip], f"static_{i}"):
                    clips.append(clip)

        if not clips:
            return False

        # 2. Concat
        list_file = os.path.join(tmp, "list.txt")
        with open(list_file,"w") as f:
            for c in clips: f.write(f"file '{c}'\n")
        concat = os.path.join(tmp, "concat.mp4")
        if not ffmpeg(["ffmpeg","-y","-f","concat","-safe","0",
                       "-i",list_file,"-c","copy",concat], "concat"):
            return False

        # 3. Add audio
        with_audio = os.path.join(tmp, "audio.mp4")
        if not ffmpeg(["ffmpeg","-y","-i",concat,"-i",audio,
                       "-c:v","copy","-c:a","aac","-b:a","192k",
                       "-shortest", with_audio], "audio"):
            return False

        # 4. Burn subtitles
        srt = os.path.join(tmp, "subs.srt")
        make_srt(scenes[:len(images)], audio_dur, srt)

        success = ffmpeg([
            "ffmpeg","-y","-i",with_audio,
            "-vf",(f"subtitles={srt}:force_style='"
                   f"FontSize={SUBTITLE_FONT_SIZE},"
                   f"PrimaryColour=&H00FFFFFF,"
                   f"OutlineColour=&H00000000,"
                   f"BackColour=&H80000000,"
                   f"Outline=2,Shadow=1,Alignment=2,MarginV=80'"),
            "-c:a","copy","-c:v","libx264","-preset","fast","-crf","23", output
        ], "subtitles")

        if not success:
            shutil.copy(with_audio, output)  # save without subtitles as fallback

        log.info(f"✅ Video: {output}")
        return True


# ══════════════════════════════════════════════════════════════
#  YOUTUBE UPLOAD
# ══════════════════════════════════════════════════════════════

def get_youtube():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(YOUTUBE_TOKEN_FILE):
        with open(YOUTUBE_TOKEN_FILE,"rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CLIENT_SECRETS, YOUTUBE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(YOUTUBE_TOKEN_FILE,"wb") as f:
            pickle.dump(creds, f)

    return build("youtube","v3",credentials=creds)


def upload_to_youtube(video_path: str, title: str, description: str,
                      tags: list, category_id: str) -> str | None:
    try:
        from googleapiclient.http import MediaFileUpload
        yt   = get_youtube()
        desc = f"{description}\n\n" + " ".join(f"#{t}" for t in tags[:10]) + "\n\n#Shorts"
        body = {
            "snippet": {"title": title[:100], "description": desc[:5000],
                        "tags": tags[:500], "categoryId": category_id},
            "status":  {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
        }
        media   = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
        request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        resp    = None
        while resp is None:
            _, resp = request.next_chunk()
        url = f"https://www.youtube.com/shorts/{resp['id']}"
        log.info(f"✅ Uploaded: {url}")
        return url
    except Exception as e:
        log.error(f"Upload failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════
#  SCHEDULER
# ══════════════════════════════════════════════════════════════

SCHEDULE_FILE = "logs/schedule.json"

def wat_now() -> datetime:
    return datetime.now(pytz.timezone("Africa/Lagos"))

def load_sched() -> dict:
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE) as f: return json.load(f)
    return {}

def save_sched(s: dict):
    with open(SCHEDULE_FILE,"w") as f: json.dump(s, f, indent=2)

def slot_used(channel_key: str, slot: str) -> bool:
    key = f"{channel_key}_{wat_now().strftime('%Y-%m-%d')}_{slot}"
    return load_sched().get(key, {}).get("used", False)

def mark_slot(channel_key: str, slot: str, title: str):
    s   = load_sched()
    key = f"{channel_key}_{wat_now().strftime('%Y-%m-%d')}_{slot}"
    s[key] = {"used": True, "title": title, "time": wat_now().isoformat()}
    save_sched(s)

def free_slots(channel_key: str) -> list:
    return [s for s in CHANNELS[channel_key]["posting_times"] if not slot_used(channel_key, s)]


# ══════════════════════════════════════════════════════════════
#  MASTER PIPELINE
# ══════════════════════════════════════════════════════════════

def run_pipeline(channel_key: str):
    ch    = CHANNELS[channel_key]
    name  = ch["name"]
    log.info(f"{'='*55}\n  PIPELINE — {name}\n{'='*55}")
    tg_start(name)

    made, uploaded = 0, 0
    slots = free_slots(channel_key)

    if not slots:
        log.info(f"No slots left today for {name}")
        return

    # STEP 1: Trends
    log.info("STEP 1 — Fetching trends")
    trends = get_trends(channel_key)

    # STEP 2: Score
    log.info("STEP 2 — Scoring topics")
    topics = select_top_topics(trends, channel_key)

    for i, topic_data in enumerate(topics):
        if i >= len(slots): break
        slot  = slots[i]
        topic = topic_data["topic"]
        log.info(f"\n─── Video {i+1} | Slot {slot} | {topic}")

        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe      = re.sub(r'[^\w\s-]','',topic)[:35].strip().replace(" ","_")
        vid_dir   = os.path.join(ch["output_dir"], f"{ts}_{safe}")
        audio_out = os.path.join(vid_dir, "voice.mp3")
        video_out = os.path.join(vid_dir, "final.mp4")
        img_dir   = os.path.join(vid_dir, "images")
        os.makedirs(vid_dir, exist_ok=True)

        try:
            # STEP 3: Hooks
            log.info("STEP 3 — Generating hooks")
            hooks = generate_hooks(topic, channel_key)
            hook  = hooks.get("best_hook_text", f"You won't believe: {topic}")

            # STEP 4: Script
            log.info("STEP 4 — Generating script")
            script = generate_script(topic, hook, channel_key)
            if not script: raise ValueError("Script failed")
            scenes    = script.get("scenes", [])
            narration = script.get("full_narration","")
            if not scenes: raise ValueError("No scenes")

            # STEP 5: SEO
            log.info("STEP 5 — Generating SEO")
            seo   = generate_seo(topic, narration, channel_key)
            title = seo.get("title", topic)
            desc  = seo.get("description","")
            tags  = seo.get("tags", ch["seo"]["default_tags"])

            # STEP 6: Voiceover
            log.info("STEP 6 — Generating voiceover")
            if not generate_voiceover(narration, channel_key, audio_out):
                raise ValueError("Voiceover failed")

            # STEP 7: Images
            log.info("STEP 7 — Generating images")
            images = generate_all_images(scenes, img_dir)
            if not images: raise ValueError("No images generated")

            # STEP 8: Assemble video
            log.info("STEP 8 — Assembling video")
            if not assemble_video(images, scenes, audio_out, video_out):
                raise ValueError("Video assembly failed")

            made += 1
            tg_created(name, title)

            # STEP 9: Upload
            log.info("STEP 9 — Uploading to YouTube")
            url = upload_to_youtube(video_out, title, desc, tags, ch["seo"]["category_id"])
            if url:
                uploaded += 1
                mark_slot(channel_key, slot, title)
                tg_uploaded(name, title, url)
            else:
                tg_error(name, "Upload", f"Failed: {title}")

        except Exception as e:
            log.error(f"Pipeline error: {e}")
            tg_error(name, f"Video {i+1}", str(e))
            continue

    tg_summary(name, made, uploaded)
    tg_done(name)
    log.info(f"DONE — Created: {made} | Uploaded: {uploaded}")


# ══════════════════════════════════════════════════════════════
#  YOUTUBE AUTH SETUP (run with: python youtube_bot.py auth)
# ══════════════════════════════════════════════════════════════

def run_auth_setup():
    print("="*50)
    print("  YouTube Bot — One-Time Auth Setup")
    print("="*50)
    if not os.path.exists(YOUTUBE_CLIENT_SECRETS):
        print(f"\n❌ {YOUTUBE_CLIENT_SECRETS} not found!")
        print("Place your client_secrets.json in the same folder as this file.")
        return
    print("\n🌐 Opening browser for Google login...")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow  = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CLIENT_SECRETS, YOUTUBE_SCOPES)
    creds = flow.run_local_server(port=0)
    with open(YOUTUBE_TOKEN_FILE,"wb") as f:
        pickle.dump(creds, f)
    print(f"\n✅ Auth complete! Token saved to: {YOUTUBE_TOKEN_FILE}")
    print("Upload this token.json file to your Oracle Cloud server.")


# ══════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # Run auth setup if requested
    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        run_auth_setup()
        sys.exit(0)

    log.info("╔══════════════════════════════════════╗")
    log.info("║   YouTube Automation Bot — STARTED   ║")
    log.info("║   Past Shock + Soul Flare             ║")
    log.info("╚══════════════════════════════════════╝")
    tg("🤖 <b>YouTube Bot Started</b>\n📺 Past Shock + Soul Flare\n⏰ Waiting for scheduled times...")

    # Schedule Past Shock — 4 videos/day (WAT)
    for t in CHANNELS["past_shock"]["posting_times"]:
        schedule.every().day.at(t).do(run_pipeline, channel_key="past_shock")
        log.info(f"Scheduled Past Shock at {t} WAT")

    # Schedule Soul Flare — 2 videos/day (WAT)
    for t in CHANNELS["soul_flare"]["posting_times"]:
        schedule.every().day.at(t).do(run_pipeline, channel_key="soul_flare")
        log.info(f"Scheduled Soul Flare at {t} WAT")

    log.info("Scheduler running. Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(30)
