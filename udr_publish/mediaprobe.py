"""Contrôle des masters vidéo avec ffprobe.

Format exigé (masters UDR) : MP4, H.264, 1080×1920 (vertical) ou 1920×1080
(horizontal), 25 i/s, AAC stéréo 128 kbit/s. Un fichier conforme est aussi
accepté tel quel par Post For Me, qui ne le réencode donc pas (critères de
trigger/ffmpeg-process-video.ts : débit ≤ 25 Mbit/s, ≤ 300 Mo, audio AAC
126–130 kbit/s, ≤ 2 canaux, ≤ 48 kHz).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

EXPECTED_SIZE = {"vertical": (1080, 1920), "horizontal": (1920, 1080)}
EXPECTED_FPS = 25
MAX_FILE_BYTES = 300 * 1024 * 1024
MAX_BITRATE = 25_000_000
AUDIO_BITRATE_RANGE = (126_000, 130_000)
MAX_SAMPLE_RATE = 48_000


@dataclass
class ProbeResult:
    ok: bool
    problems: list[str]
    summary: str


def _ffprobe(path: Path) -> dict:
    binary = shutil.which("ffprobe")
    if not binary:
        raise RuntimeError("ffprobe introuvable : installez ffmpeg pour valider les vidéos")
    out = subprocess.run(
        [binary, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe n'a pas pu lire le fichier : {out.stderr.strip()[:300]}")
    return json.loads(out.stdout)


def _rotation(stream: dict) -> int:
    for key in ("rotation",):
        if key in stream:
            return int(float(stream[key]))
    tags = stream.get("tags") or {}
    if "rotate" in tags:
        return int(float(tags["rotate"]))
    for side in stream.get("side_data_list") or []:
        if side.get("side_data_type") == "Display Matrix" and "rotation" in side:
            return int(float(side["rotation"]))
    return 0


def _fraction(value: str | None) -> Fraction | None:
    try:
        f = Fraction(value)  # "25/1"
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return f if f > 0 else None


def probe(path: Path, slot: str) -> ProbeResult:
    problems: list[str] = []
    try:
        size_bytes = path.stat().st_size
        data = _ffprobe(path)
    except (OSError, RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        return ProbeResult(False, [str(exc)], "illisible")

    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    videos = [s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")]
    audios = [s for s in streams if s.get("codec_type") == "audio"]

    if "mp4" not in (fmt.get("format_name") or ""):
        problems.append(f"conteneur {fmt.get('format_name')!r} : MP4 attendu")
    if size_bytes > MAX_FILE_BYTES:
        problems.append(f"fichier de {size_bytes / 1e6:.0f} Mo : 300 Mo maximum")
    bitrate = int(fmt.get("bit_rate") or 0)
    if bitrate > MAX_BITRATE:
        problems.append(f"débit {bitrate / 1e6:.1f} Mbit/s : 25 Mbit/s maximum")

    summary = "?"
    if len(videos) != 1:
        problems.append(f"{len(videos)} piste(s) vidéo : une seule attendue")
    else:
        v = videos[0]
        if v.get("codec_name") != "h264":
            problems.append(f"codec vidéo {v.get('codec_name')!r} : H.264 attendu")
        width, height = int(v.get("width") or 0), int(v.get("height") or 0)
        rotation = _rotation(v)
        if rotation % 180:
            width, height = height, width
        if rotation % 360:
            problems.append(f"métadonnée de rotation ({rotation}°) : exporter sans rotation")
        expected = EXPECTED_SIZE[slot]
        if (width, height) != expected:
            problems.append(f"dimensions {width}×{height} : {expected[0]}×{expected[1]} attendu pour la vidéo {slot}")
        avg = _fraction(v.get("avg_frame_rate"))
        duration = float(fmt.get("duration") or v.get("duration") or 0)
        frames = int(v.get("nb_frames") or 0)
        # Même calcul que Post For Me, puis contrôle strict de la cadence déclarée.
        fps_pfm = round(frames / duration) if frames and duration else (round(float(avg)) if avg else 0)
        if fps_pfm != EXPECTED_FPS or avg is None or abs(float(avg) - EXPECTED_FPS) > 0.01:
            problems.append(f"cadence {float(avg) if avg else '?'} i/s : {EXPECTED_FPS} i/s attendu")
        if v.get("pix_fmt") not in (None, "yuv420p"):
            problems.append(f"format de pixel {v.get('pix_fmt')!r} : yuv420p attendu")
        summary = f"{width}×{height}, {v.get('codec_name')}, {float(avg) if avg else '?'} i/s, {duration:.1f} s"

    if len(audios) != 1:
        problems.append(f"{len(audios)} piste(s) audio : une piste AAC stéréo attendue")
    else:
        a = audios[0]
        if a.get("codec_name") != "aac":
            problems.append(f"codec audio {a.get('codec_name')!r} : AAC attendu")
        if int(a.get("channels") or 0) != 2:
            problems.append(f"{a.get('channels')} canal(aux) audio : stéréo attendu")
        if int(a.get("sample_rate") or 0) > MAX_SAMPLE_RATE:
            problems.append(f"échantillonnage {a.get('sample_rate')} Hz : 48 kHz maximum")
        abr = int(a.get("bit_rate") or 0)
        low, high = AUDIO_BITRATE_RANGE
        if not low <= abr <= high:
            problems.append(f"débit audio {abr / 1000:.0f} kbit/s : 128 kbit/s attendu")

    return ProbeResult(not problems, problems, summary)
