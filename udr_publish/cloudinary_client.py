"""Upload signé des vidéos sur Cloudinary.

On utilise toujours la `secure_url` versionnée renvoyée par l'API après
l'upload (…/video/upload/v<version>/…), jamais une URL reconstruite.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

CHUNK_SIZE = 20 * 1024 * 1024  # Cloudinary : ≥ 5 Mo par morceau, sauf le dernier


class CloudinaryError(Exception):
    pass


@dataclass
class UploadResult:
    secure_url: str
    version: int
    public_id: str
    bytes: int


def sign(params: dict[str, str], api_secret: str, algorithm: str = "sha1") -> str:
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] not in ("", None))
    digest = hashlib.new(algorithm)
    digest.update((to_sign + api_secret).encode("utf-8"))
    return digest.hexdigest()


class CloudinaryClient:
    def __init__(self, session, cloud_name: str, api_key: str | None, api_secret: str | None,
                 signature_algorithm: str = "sha1", timeout: float = 600):
        self.session = session
        self.cloud_name = cloud_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.algorithm = signature_algorithm
        self.timeout = timeout

    @property
    def upload_url(self) -> str:
        return f"https://api.cloudinary.com/v1_1/{self.cloud_name}/video/upload"

    def upload_video(self, path: Path, public_id: str) -> UploadResult:
        if not (self.api_key and self.api_secret):
            raise CloudinaryError("identifiants Cloudinary absents (CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET)")
        params = {"public_id": public_id, "overwrite": "true", "timestamp": str(int(time.time()))}
        form = {**params, "api_key": self.api_key,
                "signature": sign(params, self.api_secret, self.algorithm)}
        if self.algorithm != "sha1":
            form["signature_algorithm"] = self.algorithm

        total = path.stat().st_size
        upload_id = uuid.uuid4().hex
        body: dict = {}
        with path.open("rb") as fh:
            start = 0
            while True:
                chunk = fh.read(CHUNK_SIZE)
                end = start + len(chunk) - 1
                headers = {}
                if total > CHUNK_SIZE:
                    headers = {"X-Unique-Upload-Id": upload_id,
                               "Content-Range": f"bytes {start}-{end}/{total}"}
                response = self.session.post(
                    self.upload_url, data=form, headers=headers,
                    files={"file": (path.name, chunk, "video/mp4")}, timeout=self.timeout,
                )
                body = _json(response)
                if response.status_code >= 400:
                    message = (body.get("error") or {}).get("message") if isinstance(body, dict) else None
                    raise CloudinaryError(f"HTTP {response.status_code} : {message or response.text[:500]}")
                start = end + 1
                if start >= total or not chunk:
                    break

        secure_url = body.get("secure_url")
        version = body.get("version")
        if not secure_url or version is None:
            raise CloudinaryError(f"réponse Cloudinary inattendue : {str(body)[:500]}")
        if f"/v{version}/" not in secure_url:
            raise CloudinaryError(f"URL renvoyée non versionnée : {secure_url}")
        return UploadResult(secure_url, int(version), body.get("public_id", public_id), int(body.get("bytes") or total))


def _json(response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
