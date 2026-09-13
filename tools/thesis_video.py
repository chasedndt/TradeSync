"""Render an edition's narration and a slide video, the way ChaseOS already does it.

ChaseOS's working pipeline (``hermes-home/scripts/generate_year2_term1_videos.py``)
is Pillow slides, Microsoft Edge neural TTS through ``edge-tts`` (the fleet's
configured provider, voice ``en-US-AriaNeural``), and ffmpeg for the encode,
the concat and the subtitle mux. This is the same four primitives applied to
a thesis edition.

Runs on the Windows host (ffmpeg is on PATH there; the project venv has
edge-tts and Pillow). For each edition without media:

1. fetch the edition from state-api,
2. one slide per symbol (verdict, regime, read, anchors, invalidation,
   active conditions) plus a title and a closing slide,
3. narrate each slide's part of the spoken script,
4. encode each slide+narration segment, concat, mux an SRT,
5. write everything under ``EDITIONS_HOST_DIR/<edition_id>/`` and attach the
   filenames to the edition.

Usage: python tools/thesis_video.py [--once] [--edition-id ID] [--audio-only]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path

import sys

import httpx
from PIL import Image, ImageDraw, ImageFont

# Under pythonw.exe (no console window) there is no stdout; log to a file instead.
if sys.stdout is None or sys.stderr is None:
    _log = Path(os.getenv("TRADESYNC_LOG_DIR", r"E:\Projects\TradeSync\dashboard-runtime\logs")) / "thesis_video.log"
    _log.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(_log, "a", encoding="utf-8", buffering=1)

STATE_API = os.getenv("STATE_API_URL", "http://localhost:8000").rstrip("/")
OUT_ROOT = Path(os.getenv("EDITIONS_HOST_DIR", r"E:\Projects\TradeSync\dashboard-runtime\editions"))
VOICE = os.getenv("THESIS_TTS_VOICE", "en-US-AriaNeural")  # the fleet's configured edge-tts voice
W, H, FPS = 1280, 720, 15
BG, PANEL, ACCENT, TEXT, MUTED, RED, AMBER = "#0a111b", "#101b2a", "#5aa0ff", "#e6edf5", "#8a9bb0", "#e0574a", "#e3b23c"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), ("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=f) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def render_slide(path: Path, title: str, bullets: list[str], footer: str, idx: int, total: int, tone: str = ACCENT) -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((48, 48, W - 48, H - 48), fill=PANEL, outline="#22344a")
    d.rectangle((48, 48, 60, H - 48), fill=tone)
    d.text((88, 72), "MARKET COMMAND · PRIVATE THESIS", font=font(18), fill=MUTED)
    d.text((88, 104), title, font=font(40, bold=True), fill=TEXT)
    y = 176
    for b in bullets[:7]:
        for i, line in enumerate(wrap(d, b, font(26), W - 200)):
            d.text((100 if i else 88, y), ("" if i else "•  ") + line, font=font(26), fill=TEXT)
            y += 36
        y += 6
    d.text((88, H - 92), footer, font=font(18), fill=MUTED)
    d.rectangle((88, H - 62, W - 88, H - 58), fill="#22344a")
    d.rectangle((88, H - 62, 88 + int((W - 176) * idx / max(1, total)), H - 58), fill=tone)
    img.save(path)


def slides_for(edition: dict) -> list[tuple[str, list[str], str, str]]:
    """(title, bullets, narration, tone) per slide, from the stored theses and script."""
    theses = edition.get("theses") or {}
    parts = edition["narration"].split("\n")
    out = [(f"{edition['edition'].replace('-', ' ').title()} edition", [edition["headline"]], "\n".join(parts[:2]), ACCENT)]
    cursor = 2
    for symbol in edition["symbols"]:
        t = theses.get(symbol) or {}
        s, a, inv = t.get("structure") or {}, t.get("anchors") or {}, t.get("invalidation") or {}
        active = [c["code"].replace("_", " ") for c in t.get("no_trade_conditions", []) if c.get("active")]
        bullets = [
            f"Verdict: {t.get('verdict', '—')}",
            f"Entry regime {s.get('entry_regime', 'unknown')} · paper read {s.get('direction', 'NONE')}"
            + (f" · coverage {t.get('confidence', {}).get('evidence_coverage'):.2f}" if (t.get("confidence") or {}).get("evidence_coverage") is not None else ""),
        ]
        if a.get("last_close") is not None:
            bullets.append(f"Last {a['last_close']:,.2f} · 24h {a.get('low_24h', 0):,.2f} – {a.get('high_24h', 0):,.2f} · 1h {a.get('low_1h', 0):,.2f} – {a.get('high_1h', 0):,.2f}")
        if inv.get("level") is not None:
            bullets.append(f"Invalidation {inv['level']:,.2f}")
        bullets.append("Active: " + (", ".join(active) if active else "none"))
        # the script's lines for this symbol run until the next symbol's name line
        block = []
        while cursor < len(parts) and not (block and parts[cursor].endswith(".") and parts[cursor].rstrip(".") in _NAMES):
            block.append(parts[cursor])
            cursor += 1
        tone = RED if t.get("verdict") == "NO TRADE" else AMBER
        out.append((symbol, bullets, "\n".join(block), tone))
    out.append(("End of edition", ["Private thesis. Not for publication.", "Assembled from measured evidence only; every line names its source."], parts[-1] if parts else "", ACCENT))
    return out


_NAMES = {"Bitcoin", "Ether", "Solana", "X R P", "Hype", "Zcash", "Near", "Pump", "Chainlink", "Uniswap", "End of edition"}


async def narrate(text: str, path: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text, VOICE, rate="-5%", pitch="-2Hz").save(str(path))


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def srt_time(s: float) -> str:
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(sec):02d},{int((sec - int(sec)) * 1000):03d}"


def render(edition: dict, audio_only: bool) -> dict[str, str]:
    out = OUT_ROOT / edition["id"]
    out.mkdir(parents=True, exist_ok=True)
    slides = slides_for(edition)
    segments, srt, t = [], [], 0.0
    for i, (title, bullets, script, tone) in enumerate(slides):
        audio = out / f"audio_{i:02d}.mp3"
        asyncio.run(narrate(script or title, audio))
        dur = duration(audio)
        srt.append(f"{i + 1}\n{srt_time(t)} --> {srt_time(t + dur)}\n{(script or title).replace(chr(10), ' ')}\n")
        t += dur
        if not audio_only:
            png = out / f"slide_{i:02d}.png"
            render_slide(png, title, bullets, f"{edition['edition']} · {edition['generated_at'][:16].replace('T', ' ')} UTC · slide {i + 1} of {len(slides)}", i + 1, len(slides), tone)
            seg = out / f"segment_{i:02d}.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png), "-i", str(audio), "-t", f"{dur:.3f}",
                            "-vf", f"scale={W}:{H},format=yuv420p", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-b:v", "900k",
                            "-c:a", "aac", "-b:a", "96k", "-shortest", str(seg)], check=True)
            segments.append(seg)
    # one narration file for the audio player
    concat_audio = out / "narration_list.txt"
    concat_audio.write_text("".join(f"file '{(out / f'audio_{i:02d}.mp3').as_posix()}'\n" for i in range(len(slides))), encoding="utf-8")
    narration = out / "narration.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_audio), "-c", "copy", str(narration)], check=True)
    (out / "edition.srt").write_text("\n".join(srt), encoding="utf-8")
    media = {"audio": "narration.mp3", "subtitles": "edition.srt"}
    if not audio_only:
        lst = out / "segments.txt"
        lst.write_text("".join(f"file '{s.as_posix()}'\n" for s in segments), encoding="utf-8")
        joined = out / "joined.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], check=True)
        final = out / "edition.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-i", str(out / "edition.srt"), "-c:v", "copy", "-c:a", "copy",
                        "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", str(final)], check=True)
        media["video"] = "edition.mp4"
    return media


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--edition-id")
    parser.add_argument("--audio-only", action="store_true")
    args = parser.parse_args()
    with httpx.Client(timeout=120.0, trust_env=False) as client:
        if args.edition_id:
            ids = [args.edition_id]
        else:
            listing = client.get(f"{STATE_API}/state/thesis/editions", params={"limit": 5}).json()
            ids = [e["id"] for e in listing.get("editions", []) if not e.get("media", {}).get("audio")][:1]
        if not ids:
            print("[ThesisVideo] nothing to render")
            return 0
        for eid in ids:
            edition = client.get(f"{STATE_API}/state/thesis/editions/{eid}").json()
            media = render(edition, args.audio_only)
            for kind, filename in media.items():
                client.post(f"{STATE_API}/state/thesis/editions/{eid}/media", json={"kind": kind, "filename": filename}).raise_for_status()
            print(f"[ThesisVideo] {eid}: {json.dumps(media)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
