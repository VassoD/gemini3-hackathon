"""
Lumen-Sonic — Gemini 3 Paris Hackathon 2026
GET  /           → UI
POST /analyze    → upload video, return music prompt JSON
POST /generate   → take prompt, return WAV binary
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

OUTPUT_DIR = pathlib.Path("music")
OUTPUT_DIR.mkdir(exist_ok=True)
VISION_MODEL = "gemini-3-flash-preview"
MUSIC_MODEL = "models/lyria-realtime-exp"
MUSIC_DURATION = 30  # seconds

_api_key = os.environ["GEMINI_API_KEY"]
client = genai.Client(api_key=_api_key)
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
    filename = file_storage.filename or "clip.webm"
    suffix = pathlib.Path(filename).suffix or ".webm"
    mime = "video/mp4" if suffix == ".mp4" else "video/webm"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        file_storage.save(tmp.name)
        tmp_path = tmp.name

    try:
        uploaded = client.files.upload(
            file=tmp_path,
            config=types.UploadFileConfig(mime_type=mime),
        )
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
    """Gemini vision: light → music description."""
    response = client.models.generate_content(
        model=VISION_MODEL,
        contents=[
            types.Part.from_uri(file_uri=video_file.uri, mime_type=video_file.mime_type),
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
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        wf.writeframes(raw_pcm)
    return buf.getvalue()


def make_filename(music_prompt: str) -> pathlib.Path:
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


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    """Step 1: upload video → return music prompt."""
    if "video" not in request.files:
        return jsonify(error="No video file (field: 'video')"), 400
    try:
        app.logger.info("Uploading video …")
        video_file = upload_video(request.files["video"])
        app.logger.info("Analyzing light …")
        prompt = analyze_light(video_file)
        app.logger.info("Prompt: %s", prompt)
        return jsonify(prompt=prompt)
    except Exception as exc:
        app.logger.exception("Analyze error")
        return jsonify(error=str(exc)), 500


@app.route("/generate", methods=["POST"])
def generate():
    """Step 2: music prompt → WAV binary."""
    data = request.get_json(force=True)
    prompt = (data or {}).get("prompt", "").strip()
    if not prompt:
        return jsonify(error="Missing 'prompt' field"), 400
    try:
        app.logger.info("Generating %ds track …", MUSIC_DURATION)
        audio_bytes = asyncio.run(_generate_music_async(prompt, MUSIC_DURATION))
        output_path = make_filename(prompt)
        output_path.write_bytes(audio_bytes)
        app.logger.info("Saved → %s (%d bytes)", output_path, len(audio_bytes))
        headers = {
            "Content-Disposition": f'attachment; filename="{output_path.name}"',
            "X-Music-Prompt": quote(prompt),
            "X-Output-File": output_path.name,
        }
        return Response(audio_bytes, mimetype="audio/wav", headers=headers)
    except Exception as exc:
        app.logger.exception("Generate error")
        return jsonify(error=str(exc)), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
