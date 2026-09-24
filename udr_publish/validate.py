"""Validation complète d'un pack : schéma, règles de texte, dates, vidéos.

Un pack invalide est refusé en entier : aucun réseau n'est touché.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from .mediaprobe import probe
from .networks import NETWORKS, Network
from .settings import REPO_ROOT, Settings
from .textrules import text_problems, text_warnings

SCHEMA_PATH = REPO_ROOT / "schema" / "posts.schema.json"


@dataclass
class NetworkPlan:
    network: Network
    post: dict
    media_slot: str
    scheduled_at: datetime | None   # None : brouillon sans date (date passée)
    schedule_raw: str


@dataclass
class ValidatedPack:
    pack_id: str
    title: str
    mode: str
    data: dict
    directory: Path
    plans: list[NetworkPlan]
    media_files: dict[str, Path]
    skipped: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]
    pack: ValidatedPack | None = None
    pack_id: str | None = None


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("fuseau horaire manquant")
    return dt


def _schema_errors(data: object) -> list[str]:
    validator = Draft202012Validator(load_schema())
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(racine)"
        errors.append(f"posts.json {where} : {err.message}")
    return errors


def validate_pack(
    directory: Path,
    settings: Settings,
    now: datetime | None = None,
    check_media: bool = True,
) -> ValidationResult:
    now = now or datetime.now(timezone.utc)
    errors: list[str] = []
    warnings: list[str] = []

    posts_path = directory / "posts.json"
    try:
        data = json.loads(posts_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ValidationResult(False, ["posts.json introuvable dans le pack"], [])
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return ValidationResult(False, [f"posts.json n'est pas un JSON valide : {exc}"], [])

    pack_id = data.get("id") if isinstance(data, dict) and isinstance(data.get("id"), str) else None
    schema_errors = _schema_errors(data)
    if schema_errors:
        return ValidationResult(False, schema_errors, [], pack_id=pack_id)

    publish = data["publish"]
    mode = publish.get("mode", "draft")
    if "mode" not in publish:
        warnings.append("publish.mode absent : mode draft appliqué par défaut")
    if mode == "live" and not settings.allow_live:
        errors.append(
            "mode live refusé : ce serveur n'autorise pas la publication réelle "
            "(PUBLISH_ALLOW_LIVE n'est pas activé)"
        )

    try:
        base_schedule = _parse_dt(publish["schedule"])
        linkedin_schedule = _parse_dt(publish.get("linkedin_schedule") or publish["schedule"])
    except ValueError as exc:
        return ValidationResult(False, [f"publish.schedule invalide : {exc}"], warnings, pack_id=pack_id)

    earliest = now + timedelta(minutes=settings.min_lead_minutes)
    plans: list[NetworkPlan] = []
    skipped: list[str] = []
    for network in NETWORKS:
        post = data["posts"].get(network.key)
        if post is None:
            continue
        if post.get("enabled", True) is False:
            skipped.append(network.key)
            continue
        if not network.supported:
            skipped.append(network.key)
            warnings.append(f"{network.label} : non pris en charge par Post For Me, ignoré")
            continue

        for problem in text_problems(network.key, post["text"], post.get("title")):
            errors.append(f"{network.label} : {problem}")
        for warning in text_warnings(post["text"]):
            warnings.append(f"{network.label} : {warning}")

        schedule = linkedin_schedule if network.key == "linkedin" else base_schedule
        raw = publish.get("linkedin_schedule") if network.key == "linkedin" and publish.get("linkedin_schedule") else publish["schedule"]
        scheduled_at: datetime | None = schedule
        if schedule < earliest:
            if mode == "live":
                errors.append(
                    f"{network.label} : date de publication {raw} déjà passée "
                    f"(ou à moins de {settings.min_lead_minutes} min) — pack refusé, "
                    "rien n'est publié immédiatement"
                )
            else:
                scheduled_at = None
                warnings.append(
                    f"{network.label} : date {raw} passée — brouillon créé sans date, "
                    "à fixer avant le passage en live"
                )
        plans.append(NetworkPlan(network, post, post["media"], scheduled_at, raw))

    if not plans:
        errors.append("aucun réseau actif dans posts")

    media_files: dict[str, Path] = {}
    for slot in sorted({p.media_slot for p in plans}):
        path = directory / data["media"][slot]
        if not path.is_file():
            errors.append(f"vidéo {slot} « {data['media'][slot]} » absente du pack")
            continue
        media_files[slot] = path
        if check_media:
            result = probe(path, slot)
            for problem in result.problems:
                errors.append(f"vidéo {slot} « {path.name} » : {problem}")

    if data.get("founder_comment"):
        warnings.append("founder_comment : non envoyé (Post For Me ne publie pas de commentaire)")

    if errors:
        return ValidationResult(False, errors, warnings, pack_id=pack_id)
    pack = ValidatedPack(
        pack_id=data["id"], title=data["title"], mode=mode, data=data,
        directory=directory, plans=plans, media_files=media_files, skipped=skipped,
    )
    return ValidationResult(True, [], warnings, pack=pack, pack_id=pack_id)

