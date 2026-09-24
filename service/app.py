"""Service HTTP (Railway) autour du pipeline de publication.

Le workflow n8n Cloud envoie ici le contenu du formulaire ; toute la logique
reste dans udr_publish (la même que scripts/publish.py).

  GET  /healthz                 état du service (sans authentification)
  POST /packs                   dépôt d'un pack (multipart : posts_json, video_vertical, video_horizontal)
  GET  /packs/<pack_id>/status  suivi : publié / programmé / en erreur / à vérifier

Authentification : en-tête « Authorization: Bearer <PUBLISH_SERVICE_TOKEN> ».
Sans PUBLISH_SERVICE_TOKEN configuré, le service refuse tout (503).
"""

from __future__ import annotations

import hmac
import json
import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from udr_publish.pipeline import Publisher  # noqa: E402
from udr_publish.report import valid_pack_id  # noqa: E402
from udr_publish.settings import Settings, load_settings  # noqa: E402

SAFE_NAME = re.compile(r"^[^/\\]+\.mp4$")
FIELDS = {"vertical": "video_vertical", "horizontal": "video_horizontal"}


def create_app(settings: Settings | None = None, publisher_factory=None) -> Flask:
    settings = settings or load_settings()
    publisher_factory = publisher_factory or (lambda: Publisher(settings))
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 700 * 1024 * 1024  # deux masters de 300 Mo max + posts.json

    def unauthorized():
        if not settings.service_token:
            return jsonify(error="service non configuré : PUBLISH_SERVICE_TOKEN absent"), 503
        header = request.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        if not hmac.compare_digest(token.encode(), settings.service_token.encode()):
            return jsonify(error="non autorisé"), 401
        return None

    @app.get("/healthz")
    def healthz():
        return jsonify(ok=True, live_enabled=settings.allow_live)

    @app.post("/packs")
    def deposit():
        if (denied := unauthorized()) is not None:
            return denied
        posts_file = request.files.get("posts_json")
        if posts_file is None:
            return jsonify(error="champ posts_json manquant"), 400
        incoming = settings.data_dir / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="pack-", dir=incoming))
        try:
            raw = posts_file.read()
            (work / "posts.json").write_bytes(raw)
            try:
                media = json.loads(raw).get("media") or {}
            except (ValueError, AttributeError):
                media = {}
            for slot, field in FIELDS.items():
                upload = request.files.get(field)
                if upload is None:
                    continue
                name = media.get(slot) if isinstance(media, dict) else None
                name = name if isinstance(name, str) and SAFE_NAME.match(name) else f"{field}.mp4"
                upload.save(work / name)
            rep = publisher_factory().run(work)
            return jsonify(rep), 200
        except Exception as exc:  # le rapport d'erreur part quand même par e-mail
            app.logger.error(settings.redact(traceback.format_exc()))
            message = settings.redact(f"erreur interne du service : {exc}")
            return jsonify(ok=False, refused=False, error=message,
                           report_subject="[UDR publication] erreur du service",
                           report_text=message + "\n"), 500
        finally:
            shutil.rmtree(work, ignore_errors=True)  # les vidéos vivent sur Cloudinary

    @app.get("/packs/<pack_id>/status")
    def status(pack_id: str):
        if (denied := unauthorized()) is not None:
            return denied
        if not valid_pack_id(pack_id):
            return jsonify(error="identifiant de pack invalide"), 400
        return jsonify(publisher_factory().check(pack_id)), 200

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=8000)
