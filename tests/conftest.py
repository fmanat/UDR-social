"""Fixtures : vidéos générées par ffmpeg et faux Post For Me / Cloudinary en mémoire."""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from udr_publish.settings import Settings  # noqa: E402

FAKE_API_KEY = "pfm_test_key_SECRET_123456"
FAKE_CLOUD_SECRET = "cloud_test_secret_ABCDEF"

ACCOUNTS = {
    "facebook": "spc_fb", "instagram": "spc_ig", "youtube": "spc_yt",
    "tiktok": "spc_tt", "linkedin": "spc_li", "x": "spc_x",
}


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(
        pfm_api_key=FAKE_API_KEY, pfm_auth_via_proxy=False, pfm_base_url="https://api.postforme.dev",
        pfm_team_id="team_1", pfm_project_id="proj_1", pfm_accounts=dict(ACCOUNTS),
        cloudinary_cloud_name="dl8itl9nw", cloudinary_api_key="123456789",
        cloudinary_api_secret=FAKE_CLOUD_SECRET, cloudinary_folder="udr-publish",
        cloudinary_signature_algorithm="sha1", allow_live=False, min_lead_minutes=5,
        data_dir=tmp_path / "data", service_token="service-token-XYZ-987",
        secrets=(FAKE_API_KEY, FAKE_CLOUD_SECRET, "service-token-XYZ-987"),
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


# ------------------------------------------------------------------ vidéos
def _ffmpeg(path: Path, width: int, height: int, fps: int = 25, audio: str = "128k", channels: int = 2) -> None:
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate={fps}",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", "2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", audio, "-ac", str(channels), "-ar", "48000", str(path),
    ], check=True)


@pytest.fixture(scope="session")
def videos(tmp_path_factory):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg requis pour ces tests")
    d = tmp_path_factory.mktemp("videos")
    _ffmpeg(d / "v.mp4", 1080, 1920)
    _ffmpeg(d / "h.mp4", 1920, 1080)
    _ffmpeg(d / "bad.mp4", 720, 1280, fps=30, audio="96k", channels=1)
    return d


EXAMPLE = json.loads((ROOT / "campaigns" / "UDR_memoire_territoire_V1.json").read_text(encoding="utf-8"))


@pytest.fixture
def make_pack(tmp_path, videos):
    """Crée un dossier de pack ; `mutate` modifie le posts.json d'exemple."""
    counter = {"n": 0}

    def _make(mutate=None, pack_id="UDR_test_V1", data=None) -> Path:
        counter["n"] += 1
        d = tmp_path / f"pack{counter['n']}"
        d.mkdir()
        posts = copy.deepcopy(data if data is not None else EXAMPLE)
        posts["id"] = pack_id
        posts["publish"]["schedule"] = "2030-01-01T19:30:00+01:00"
        posts["publish"]["linkedin_schedule"] = "2030-01-02T08:30:00+01:00"
        if mutate:
            mutate(posts)
        (d / "posts.json").write_text(json.dumps(posts, ensure_ascii=False), encoding="utf-8")
        media = posts.get("media", {})
        if "vertical" in media:
            shutil.copy(videos / "v.mp4", d / media["vertical"])
        if "horizontal" in media:
            shutil.copy(videos / "h.mp4", d / media["horizontal"])
        return d

    return _make


# ---------------------------------------------------------- faux services
class FakeResponse:
    def __init__(self, status: int, body):
        self.status_code = status
        self._body = body
        self.text = json.dumps(body) if not isinstance(body, str) else body

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


class FakeWorld:
    """Simule Post For Me et Cloudinary, et enregistre chaque appel."""

    def __init__(self):
        self.posts: dict[str, dict] = {}
        self.results: dict[str, list] = {}
        self.calls: list[tuple] = []
        self.uploads: list[dict] = []
        self.fail_accounts: dict[str, tuple[int, object]] = {}
        self.cloudinary_fail = False
        self.version = 1700000000

    # Cloudinary ----------------------------------------------------------
    def post(self, url, data=None, headers=None, files=None, timeout=None):
        assert url == "https://api.cloudinary.com/v1_1/dl8itl9nw/video/upload"
        assert "signature" in data and "api_key" in data and FAKE_CLOUD_SECRET not in json.dumps(data)
        self.uploads.append({"public_id": data["public_id"], "headers": headers})
        if self.cloudinary_fail:
            return FakeResponse(400, {"error": {"message": "Invalid Signature"}})
        self.version += 1
        return FakeResponse(200, {
            "public_id": data["public_id"], "version": self.version, "bytes": 1234,
            "secure_url": f"https://res.cloudinary.com/dl8itl9nw/video/upload/v{self.version}/{data['public_id']}.mp4",
        })

    # Post For Me ---------------------------------------------------------
    def request(self, method, url, headers=None, timeout=None, json=None, params=None):
        path = urlparse(url).path
        assert headers["Authorization"] == f"Bearer {FAKE_API_KEY}"
        self.calls.append((method, path, copy.deepcopy(json), dict(params or {})))
        if method == "POST" and path == "/v1/social-posts":
            return self._save(None, json)
        m = re.fullmatch(r"/v1/social-posts/(\w+)", path)
        if m and method == "PUT":
            post = self.posts.get(m.group(1))
            if post is None:
                return FakeResponse(404, {"message": "Post not found"})
            if post["status"] == "processed":
                return FakeResponse(400, {"message": "Post has already been processed"})
            return self._save(m.group(1), json)
        if m and method == "GET":
            post = self.posts.get(m.group(1))
            return FakeResponse(200, post) if post else FakeResponse(404, {"message": "Post not found"})
        if method == "GET" and path == "/v1/social-posts":
            ext = params.get("external_id")
            return FakeResponse(200, {"data": [p for p in self.posts.values() if p["external_id"] == ext],
                                      "meta": {}})
        if method == "GET" and path == "/v1/social-post-results":
            return FakeResponse(200, {"data": self.results.get(params["post_id"], []), "meta": {}})
        return FakeResponse(404, {"message": f"route inconnue {method} {path}"})

    def _save(self, post_id, body):
        account = body["social_accounts"][0]
        if account in self.fail_accounts:
            status, payload = self.fail_accounts[account]
            return FakeResponse(status, payload)
        post_id = post_id or f"sp_{len(self.posts) + 1}"
        status = "draft" if body.get("isDraft") else ("scheduled" if body.get("scheduled_at") else "processing")
        self.posts[post_id] = {"id": post_id, "status": status, "caption": body["caption"],
                               "external_id": body.get("external_id"), "scheduled_at": body.get("scheduled_at"),
                               "body": copy.deepcopy(body)}
        return FakeResponse(200, self.posts[post_id])

    def count(self, method, path_prefix="/v1/social-posts"):
        return sum(1 for c in self.calls if c[0] == method and c[1].startswith(path_prefix))


@pytest.fixture
def world():
    return FakeWorld()
