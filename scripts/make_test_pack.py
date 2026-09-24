#!/usr/bin/env python3
"""Génère un pack factice pour tester en mode draft (étape D).

Deux vidéos courtes au format des masters (H.264, 25 i/s, AAC stéréo
128 kbit/s ; 1080×1920 et 1920×1080) et un posts.json minimal : Facebook
seulement, mode draft. Le dossier est créé sous packs/ (ignoré par git).

  python scripts/make_test_pack.py                  # packs/UDR_test_<horodatage>
  python scripts/make_test_pack.py --id UDR_test_V1 --seconds 4
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def make_video(path: Path, width: int, height: int, seconds: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        sys.exit("ffmpeg introuvable")
    base = [ffmpeg, "-y", "-v", "error",
            "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", str(seconds)]
    encode = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "25",
              "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000",
              "-movflags", "+faststart", str(path)]
    label = ["-vf", "drawtext=text='TEST UDR - NE PAS PUBLIER':fontcolor=white:fontsize=64:"
                    "box=1:boxcolor=black@0.6:x=(w-text_w)/2:y=(h-text_h)/2"]
    if subprocess.run(base + label + encode).returncode != 0:
        subprocess.run(base + encode, check=True)  # sans police disponible : pas de bandeau


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--id", default=f"UDR_test_{datetime.now():%Y%m%d_%H%M%S}")
    parser.add_argument("--seconds", type=int, default=3)
    parser.add_argument("--out", type=Path, default=ROOT / "packs")
    args = parser.parse_args()

    pack_dir = args.out / args.id
    pack_dir.mkdir(parents=True, exist_ok=True)
    vertical, horizontal = f"{args.id}_9x16.mp4", f"{args.id}_16x9.mp4"
    make_video(pack_dir / vertical, 1080, 1920, args.seconds)
    make_video(pack_dir / horizontal, 1920, 1080, args.seconds)

    schedule = (datetime.now(timezone.utc) + timedelta(days=30)).replace(microsecond=0)
    posts = {
        "id": args.id,
        "title": "Pack de test — ne pas publier",
        "created": datetime.now().date().isoformat(),
        "publish": {"mode": "draft", "schedule": schedule.isoformat()},
        "media": {"vertical": vertical, "horizontal": horizontal},
        "posts": {
            "facebook": {
                "media": "horizontal",
                "text": "TEST — brouillon de vérification de l'outil de publication. Ne pas publier.",
            }
        },
        "notes": "Pack factice généré par scripts/make_test_pack.py.",
    }
    (pack_dir / "posts.json").write_text(json.dumps(posts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(pack_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
