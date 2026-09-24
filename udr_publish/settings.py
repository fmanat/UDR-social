"""Configuration lue dans l'environnement (et un fichier .env optionnel).

Aucun secret n'a de valeur par défaut dans le code. Le fichier .env n'est
jamais commité (voir .gitignore) ; en production, les variables sont posées
dans Railway.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Charge un fichier .env sans écraser les variables déjà définies."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        os.environ.setdefault(key, value)


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "oui"}


@dataclass(frozen=True)
class Settings:
    # Post For Me
    pfm_api_key: str | None
    pfm_auth_via_proxy: bool
    pfm_base_url: str
    pfm_team_id: str | None
    pfm_project_id: str | None
    pfm_accounts: dict[str, str | None]
    # Cloudinary
    cloudinary_cloud_name: str
    cloudinary_api_key: str | None
    cloudinary_api_secret: str | None
    cloudinary_folder: str
    cloudinary_signature_algorithm: str
    # Garde-fous
    allow_live: bool
    min_lead_minutes: int
    # Stockage local
    data_dir: Path
    # Service HTTP
    service_token: str | None
    secrets: tuple[str, ...] = field(default=(), repr=False)

    @property
    def journal_path(self) -> Path:
        return self.data_dir / "publish-log.jsonl"

    @property
    def locks_dir(self) -> Path:
        return self.data_dir / "locks"

    def dashboard_url(self, pfm_post_id: str) -> str | None:
        if not (self.pfm_team_id and self.pfm_project_id):
            return None
        return f"https://app.postforme.dev/{self.pfm_team_id}/{self.pfm_project_id}/posts/{pfm_post_id}"

    def redact(self, text: str) -> str:
        """Masque toute valeur secrète qui apparaîtrait dans un message."""
        for secret in self.secrets:
            if secret and len(secret) >= 6:
                text = text.replace(secret, "***")
        return text


ACCOUNT_ENV = {
    "facebook": "PFM_ACCOUNT_FACEBOOK",
    "instagram": "PFM_ACCOUNT_INSTAGRAM",
    "youtube": "PFM_ACCOUNT_YOUTUBE",
    "tiktok": "PFM_ACCOUNT_TIKTOK",
    "linkedin": "PFM_ACCOUNT_LINKEDIN",
    "x": "PFM_ACCOUNT_X",
}


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or REPO_ROOT / ".env")
    env = os.environ

    def opt(name: str) -> str | None:
        value = env.get(name, "").strip()
        return value or None

    secrets = tuple(
        v for v in (
            opt("POST_FOR_ME_API_KEY"),
            opt("CLOUDINARY_API_KEY"),
            opt("CLOUDINARY_API_SECRET"),
            opt("PUBLISH_SERVICE_TOKEN"),
        ) if v
    )
    return Settings(
        pfm_api_key=opt("POST_FOR_ME_API_KEY"),
        pfm_auth_via_proxy=_flag("PFM_AUTH_VIA_PROXY"),
        pfm_base_url=(opt("POST_FOR_ME_BASE_URL") or "https://api.postforme.dev").rstrip("/"),
        pfm_team_id=opt("PFM_TEAM_ID"),
        pfm_project_id=opt("PFM_PROJECT_ID"),
        pfm_accounts={platform: opt(var) for platform, var in ACCOUNT_ENV.items()},
        cloudinary_cloud_name=opt("CLOUDINARY_CLOUD_NAME") or "dl8itl9nw",
        cloudinary_api_key=opt("CLOUDINARY_API_KEY"),
        cloudinary_api_secret=opt("CLOUDINARY_API_SECRET"),
        cloudinary_folder=(opt("CLOUDINARY_FOLDER") or "udr-publish").strip("/"),
        cloudinary_signature_algorithm=(opt("CLOUDINARY_SIGNATURE_ALGORITHM") or "sha1").lower(),
        allow_live=_flag("PUBLISH_ALLOW_LIVE"),
        min_lead_minutes=int(opt("PUBLISH_MIN_LEAD_MINUTES") or "5"),
        data_dir=Path(opt("PUBLISH_DATA_DIR") or REPO_ROOT / "data"),
        service_token=opt("PUBLISH_SERVICE_TOKEN"),
        secrets=secrets,
    )
