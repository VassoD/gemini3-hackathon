# Lumen-Sonic

Point light at your camera. Get a matching music track back.

Built at the Gemini 3 Paris Hackathon 2026 using Gemini Vision + Lyria.

**Live demo: [https://gemini3-hackathon-production.up.railway.app](https://gemini3-hackathon-production.up.railway.app)**

---

## The Concept

Light is everywhere — sunlight through a window, a candle, an LED, a neon sign. Lumen-Sonic treats light as a musical instrument.

Point your phone at any light source. The app reads the light's physical properties — color temperature, flicker rate, brightness variations — and uses Gemini Vision to translate them into a music description. Lyria then generates a 30-second original track from that description.

The result is **synesthesia as a service**: the same light, heard instead of seen.

---

## Why light specifically?

Most video-to-music tools analyze everything — faces, objects, scenes. We constrained the model to light only, because:

- Light has direct musical analogues: warm color → warm tone, fast flicker → fast tempo, dim → quiet
- It creates an unexpected, almost magical connection — point a lamp at your phone and music appears
- It's universal: every environment has light, making the tool usable anywhere

---

## The phone as a unique musical lens

Different phones capture the same light differently — sensor size, white balance algorithms, HDR processing, exposure handling all vary by manufacturer. A Pixel filming a candle will produce different music than an iPhone filming the same candle.

This means the music isn't just about the light — it's about **you + your device + the light**. In a room of 10 people filming the same source, you get 10 different tracks.

Tested live on a **Google Pixel 10** via mobile browser (no app install required).

---

## How it works

1. Upload a video or record live via the camera tab (8 seconds)
2. Gemini Vision analyzes the light — color temperature, flicker rate, brightness arc — and writes a music prompt
3. The prompt is shown immediately in the UI (while music is still generating)
4. Lyria generates a 30-second audio track from that prompt
5. The track plays in the browser and can be downloaded as WAV

The pipeline is split into two steps (`/analyze` then `/generate`) so the user sees the music description appear mid-process — no blank waiting screen.

---

## Requirements

- Python 3.10+
- A [Gemini API key](https://aistudio.google.com/app/apikey)
- `ngrok` account (free) — only needed for mobile camera access

---

## Setup

```bash
git clone <this-repo>
cd gemini3-hackathon

pip install -r requirements.txt

export GEMINI_API_KEY=your_key_here
```

---

## Running locally on PC

```bash
python3 app.py
```

Open [http://localhost:5001](http://localhost:5001) in your browser.

Both the **Upload Video** and **Live Camera** tabs work on desktop Chrome/Firefox.

---

## Running locally on mobile (iPhone / Android)

The camera requires **HTTPS**, so you need to expose your local server via ngrok.

### 1. Install ngrok

```bash
# macOS
brew install ngrok              
# or download from https://ngrok.com/download
```

Sign up at [ngrok.com](https://ngrok.com) (free), then:

```bash
ngrok config add-authtoken <your-token>
```

### 2. Start Flask

```bash
python3 app.py
```

### 4. In a second terminal, open the tunnel

```bash
ngrok http 5001
```

ngrok prints a public URL like:

```
Forwarding  https://abc123.ngrok-free.app → http://localhost:5000
```

### 5. Open that URL on your phone

- On first visit, ngrok shows a browser warning — tap **Visit Site**
- Allow camera permission when prompted
- Use the **Live Camera** tab to record 8 seconds of light

Any phone works — Android, iPhone, any modern browser. No app install needed.

---

## Output

Generated tracks are saved to the `music/` folder (git-ignored).

---

## Future Possibilities

Everything below is achievable with the tools already in the stack (Gemini Vision + Lyria + FFmpeg).

**Video + audio merge**
Mux the recorded clip (looped to 30s) with the generated track using FFmpeg — one command — and offer a single downloadable video file ready to share on Reels or TikTok.

**Real-time light-to-music streaming**
Instead of recording a clip, send frames continuously to Gemini Vision and regenerate or extend the track on the fly. The music evolves as the light changes.

**Multi-source comparison**
Record the same light source from two different phones and generate both tracks side by side, making the "your device is your instrument" idea tangible and demonstrable.

**Prompt history / gallery**
Store generated prompts and audio URLs in a lightweight database and surface a public gallery — a feed of light moments turned into music by different people around the world.

**Lyria parameter exposure**
Gemini Vision already infers BPM, key, and instrumentation. These could be surfaced as editable sliders before generation, letting the user nudge the music while keeping the light as the creative seed.

**Timelapse mode**
Sample one frame per second from a longer video (a sunrise, a candle burning down) and stitch together a track whose mood arc mirrors the changing light over time.
