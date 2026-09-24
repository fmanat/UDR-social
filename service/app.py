"""Service HTTP (Railway) autour du pipeline de publication.

Le workflow n8n Cloud envoie ici le contenu du formulaire ; toute la logique
reste dans udr_publish (la même que scripts/publish.py).

  GET  /healthz                 état du service (sans authentification)
  POST /packs                   dépôt d'un pack (multipart : posts_json, video_vertical, video_horizontal)
  GET  /packs/<pack_id>/status  suivi : publié / programmé / en erreur / à vérifier

  GET  /depot                   page de dépôt dans le navigateur (sans n8n)
  POST /depot/envoi             dépôt depuis cette page (mêmes champs que /packs)
  GET  /depot/pack-de-test.zip  pack factice Facebook en draft, à redéposer par la page
  GET  /depot/comptes           comptes Post For Me connectés (id spc_… à poser dans PFM_ACCOUNT_*)
  GET  /depot/suivi?pack=<id>   suivi d'un pack (même rapport que /packs/<id>/status, en texte)

Authentification :
- /packs : en-tête « Authorization: Bearer <PUBLISH_SERVICE_TOKEN> ». Sans
  PUBLISH_SERVICE_TOKEN configuré, le service refuse tout (503).
- /depot : mot de passe PUBLISH_PAGE_PASSWORD demandé par le navigateur (Basic
  Auth, nom d'utilisateur libre). Sans mot de passe d'au moins 12 caractères,
  la page est désactivée (503).
"""

from __future__ import annotations

import hmac
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from udr_publish.pipeline import Publisher  # noqa: E402
from udr_publish.report import valid_pack_id  # noqa: E402
from udr_publish.settings import ACCOUNT_ENV, Settings, load_settings  # noqa: E402

SAFE_NAME = re.compile(r"^[^/\\]+\.mp4$")
FIELDS = {"vertical": "video_vertical", "horizontal": "video_horizontal"}
SERVICE_DIR = Path(__file__).resolve().parent
MAKE_TEST_PACK = SERVICE_DIR.parent / "scripts" / "make_test_pack.py"
MIN_PAGE_PASSWORD = 12


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

    def page_denied():
        password = settings.page_password or ""
        if len(password) < MIN_PAGE_PASSWORD:
            return Response("Page de dépôt désactivée : PUBLISH_PAGE_PASSWORD absent ou trop court "
                            f"({MIN_PAGE_PASSWORD} caractères minimum).\n",
                            503, mimetype="text/plain; charset=utf-8")
        auth = request.authorization
        given = (auth.password or "") if auth and auth.type == "basic" else ""
        if not hmac.compare_digest(given.encode(), password.encode()):
            return Response("Mot de passe requis.\n", 401, mimetype="text/plain; charset=utf-8",
                            headers={"WWW-Authenticate": 'Basic realm="Depot UDR", charset="UTF-8"'})
        return None

    def run_deposit():
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

    @app.post("/packs")
    def deposit():
        if (denied := unauthorized()) is not None:
            return denied
        return run_deposit()

    @app.get("/depot")
    def depot_page():
        if (denied := page_denied()) is not None:
            return denied
        return send_file(SERVICE_DIR / "depot.html", mimetype="text/html", max_age=0)

    @app.post("/depot/envoi")
    def depot_upload():
        if (denied := page_denied()) is not None:
            return denied
        # Un formulaire d'un autre site ne peut pas poser cet en-tête (pas de CSRF).
        if request.headers.get("X-UDR-Depot") != "1":
            return jsonify(error="envoi accepté uniquement depuis la page /depot"), 400
        return run_deposit()

    @app.get("/depot/pack-de-test.zip")
    def depot_test_pack():
        if (denied := page_denied()) is not None:
            return denied
        pack_id = f"UDR_test_{datetime.now():%Y%m%d_%H%M%S}"
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run([sys.executable, str(MAKE_TEST_PACK), "--id", pack_id, "--out", tmp],
                                  capture_output=True, text=True, timeout=300)
            if done.returncode != 0:
                app.logger.error(done.stderr)
                return Response("Impossible de générer le pack de test (ffmpeg).\n", 500,
                                mimetype="text/plain; charset=utf-8")
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
                for path in sorted((Path(tmp) / pack_id).iterdir()):
                    archive.write(path, f"{pack_id}/{path.name}")
        buffer.seek(0)
        return send_file(buffer, mimetype="application/zip", as_attachment=True,
                         download_name=f"{pack_id}.zip")

    @app.get("/depot/comptes")
    def depot_accounts():
        if (denied := page_denied()) is not None:
            return denied
        lines = ["Comptes connectés chez Post For Me (id à copier dans la variable Railway indiquée)", ""]
        try:
            accounts = publisher_factory().pfm.list_accounts()
        except Exception as exc:
            lines.append(settings.redact(f"Lecture impossible : {exc}"))
            lines.append("Vérifier POST_FOR_ME_API_KEY dans Railway.")
            return Response("\n".join(lines) + "\n", 502, mimetype="text/plain; charset=utf-8")
        if not accounts:
            lines.append("Aucun compte connecté.")
        for account in accounts:
            platform = str(account.get("platform") or "")
            variable = ACCOUNT_ENV.get(platform.split("_")[0], "")
            configured = settings.pfm_accounts.get(platform.split("_")[0]) == account.get("id")
            lines.append(f"{platform:<12} {account.get('id') or '':<32} {account.get('username') or ''}"
                         f" ({account.get('status') or '?'})")
            if variable:
                lines.append(f"{'':<12} → {variable}" + (" : déjà en place" if configured else ""))
        return Response("\n".join(lines) + "\n", 200, mimetype="text/plain; charset=utf-8")

    @app.get("/depot/suivi")
    def depot_status():
        if (denied := page_denied()) is not None:
            return denied
        pack_id = (request.args.get("pack") or "").strip()
        if not valid_pack_id(pack_id):
            return Response("Identifiant de pack invalide.\n", 400, mimetype="text/plain; charset=utf-8")
        rep = publisher_factory().check(pack_id)
        return Response(rep["report_text"], 200, mimetype="text/plain; charset=utf-8")

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
