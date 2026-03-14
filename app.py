"""
Lumen-Sonic — Gemini 3 Paris Hackathon 2026
POST /process  →  upload 10s light video  →  jardin_vibe.wav
"""

import asyncio
import datetime
import io
import os
import pathlib
import re
import tempfile
import time
import wave

from urllib.parse import quote

from flask import Flask, jsonify, render_template, request, Response
from google import genai
from google.genai import types

app = Flask(__name__)

OUTPUT_DIR = pathlib.Path(".")
VISION_MODEL = "gemini-3-flash-preview"
MUSIC_MODEL = "models/lyria-realtime-exp"
MUSIC_DURATION = 30  # seconds

_api_key = os.environ["GEMINI_API_KEY"]
client = genai.Client(api_key=_api_key)
# Lyria's BidiGenerateMusic WebSocket lives on v1alpha, not v1beta
music_client = genai.Client(
    api_key=_api_key,
    http_options=types.HttpOptions(api_version="v1alpha"),
)

VISION_PROMPT = """
You are a synesthesia engine that maps visual light properties to music.

Analyze this video clip of light (sunlight or LED). Describe in one rich paragraph
(≤ 120 words) the musical piece that should accompany it. Include:
- Tempo (BPM range) suggested by the flicker / pulse rate
- Mood / atmosphere inferred from colour temperature (warm ≈ low Kelvin, cool ≈ high Kelvin)
- Instrumentation that mirrors the light quality (e.g. soft piano for diffuse sunlight,
  arpeggiated synth for rapid LED flicker)
- Dynamics: intensity arc that matches the brightness variations

Return ONLY the music generation prompt, no preamble, no bullet points.
"""


def upload_video(file_storage) -> genai.types.File:
    """Write the incoming file to a temp path and upload via Files API."""
    suffix = pathlib.Path(file_storage.filename or "clip.mp4").suffix or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        file_storage.save(tmp.name)
        tmp_path = tmp.name

    try:
        uploaded = client.files.upload(
            file=tmp_path,
            config=types.UploadFileConfig(mime_type="video/mp4"),
        )
        # Poll until the file is fully processed
        for _ in range(30):
            file_info = client.files.get(name=uploaded.name)
            if file_info.state == types.FileState.ACTIVE:
                return file_info
            if file_info.state == types.FileState.FAILED:
                raise RuntimeError(f"File processing failed: {file_info.name}")
            time.sleep(2)
        raise TimeoutError("Video file did not become ACTIVE within 60 s")
    finally:
        os.unlink(tmp_path)


def analyze_light(video_file: genai.types.File) -> str:
    """Step 1 — Gemini vision: light → music description."""
    response = client.models.generate_content(
        model=VISION_MODEL,
        contents=[
            types.Part.from_uri(file_uri=video_file.uri, mime_type="video/mp4"),
            VISION_PROMPT,
        ],
    )
    return response.text.strip()


async def _generate_music_async(music_prompt: str, duration: int) -> bytes:
    """Streams audio from Lyria via the Live Music WebSocket API."""
    audio_parts: list[bytes] = []
    deadline = time.monotonic() + duration

    async with music_client.aio.live.music.connect(model=MUSIC_MODEL) as session:
        await session.set_weighted_prompts(
            [types.WeightedPrompt(text=music_prompt, weight=1.0)]
        )
        await session.play()

        async for message in session.receive():
            if message.server_content and message.server_content.audio_chunks:
                for chunk in message.server_content.audio_chunks:
                    if chunk.data:
                        audio_parts.append(chunk.data)
            if time.monotonic() >= deadline:
                await session.stop()
                break

    if not audio_parts:
        raise RuntimeError("Lyria returned no audio chunks")
    raw_pcm = b"".join(audio_parts)

    # Wrap raw PCM in a WAV container (Lyria: 16-bit stereo, 48 kHz)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)       # stereo
        wf.setsampwidth(2)       # 16-bit
        wf.setframerate(48000)   # 48 kHz
        wf.writeframes(raw_pcm)
    return buf.getvalue()


def generate_music(music_prompt: str) -> bytes:
    """Step 2 — Lyria: music description → audio bytes (sync wrapper)."""
    return asyncio.run(_generate_music_async(music_prompt, MUSIC_DURATION))


def make_filename(music_prompt: str) -> pathlib.Path:
    """Ask the model for a short evocative name, then append a datetime stamp."""
    resp = client.models.generate_content(
        model=VISION_MODEL,
        contents=(
            f"Given this music description, invent a short evocative title (2-4 words, "
            f"no punctuation). Return ONLY the title, nothing else.\n\n{music_prompt}"
        ),
    )
    raw = resp.text.strip()
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_").lower()
    slug = slug[:40] or "lumen_sonic"
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"{slug}_{stamp}.wav"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    if "video" not in request.files:
        return jsonify(error="No video file provided (field name: 'video')"), 400

    video_file_storage = request.files["video"]

    try:
        # 1. Upload video to Files API
        app.logger.info("Uploading video …")
        video_file = upload_video(video_file_storage)

        # 2. Vision analysis
        app.logger.info("Analyzing light with %s …", VISION_MODEL)
        music_prompt = analyze_light(video_file)
        app.logger.info("Music prompt: %s", music_prompt)

        # 3. Music generation
        app.logger.info("Generating %ds track with %s …", MUSIC_DURATION, MUSIC_MODEL)
        audio_bytes = generate_music(music_prompt)

        # 4. Save output + stream back to browser
        output_path = make_filename(music_prompt)
        output_path.write_bytes(audio_bytes)
        app.logger.info("Saved → %s (%d bytes)", output_path, len(audio_bytes))

        headers = {
            "Content-Disposition": f'attachment; filename="{output_path.name}"',
            "X-Music-Prompt": quote(music_prompt),
            "X-Output-File": output_path.name,
        }
        return Response(audio_bytes, mimetype="audio/wav", headers=headers)

    except (RuntimeError, TimeoutError) as exc:
        app.logger.error("Processing error: %s", exc)
        return jsonify(error=str(exc)), 500
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("Unexpected error")
        return jsonify(error=str(exc)), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
