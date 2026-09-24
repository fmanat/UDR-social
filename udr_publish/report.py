"""Rapport par réseau : structure JSON + rendu texte (e-mail, terminal)."""

from __future__ import annotations

import json
import re

from .journal import utcnow
from .networks import Network

BROUILLON = "brouillon"
BROUILLON_MAJ = "brouillon mis à jour"
BROUILLON_INCHANGE = "brouillon inchangé"
PROGRAMME = "programmé"
PUBLIE = "publié"
EN_COURS = "en cours"
A_VERIFIER = "à vérifier"
ERREUR = "en erreur"
DEJA_ENVOYE = "déjà envoyé"
SIMULATION = "simulation"

_PACK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")


def valid_pack_id(pack_id: str) -> bool:
    return bool(_PACK_ID.match(pack_id))


def _base(kind: str, pack_id: str | None) -> dict:
    return {"kind": kind, "pack_id": pack_id, "generated_at": utcnow(), "ok": True,
            "refused": False, "errors": [], "warnings": [], "media": {}, "networks": []}


def new_report(pack, warnings: list[str], dry_run: bool) -> dict:
    rep = _base("simulation" if dry_run else "depot", pack.pack_id)
    rep.update(title=pack.title, mode=pack.mode, warnings=list(warnings), skipped=list(pack.skipped))
    return rep


def refused_report(pack_id: str | None, errors: list[str], warnings: list[str]) -> dict:
    rep = _base("depot", pack_id)
    rep.update(ok=False, refused=True, errors=list(errors), warnings=list(warnings))
    return finalize(rep)


def status_report(pack_id: str) -> dict:
    return _base("suivi", pack_id)


def add_network(rep: dict, network: Network, status: str, message: str, *, pfm_post_id: str | None = None,
                scheduled_at: str | None = None, links: dict | None = None, api_error: str = "",
                payload: dict | None = None) -> None:
    entry = {"network": network.key, "label": network.label, "status": status, "message": message,
             "pfm_post_id": pfm_post_id, "scheduled_at": scheduled_at, "links": links or {},
             "api_error": api_error}
    if payload is not None:
        entry["payload"] = payload
    rep["networks"].append(entry)


def finalize(rep: dict) -> dict:
    counts: dict[str, int] = {}
    for entry in rep["networks"]:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    rep["summary"] = counts
    if any(e["status"] == ERREUR for e in rep["networks"]) or rep["errors"]:
        rep["ok"] = False
    rep["report_subject"] = subject(rep)
    rep["report_text"] = render_text(rep)
    return rep


def status_from_api(api_status: str, action: str) -> str:
    if api_status == "draft":
        return BROUILLON_MAJ if action == "updated" else BROUILLON
    if api_status == "scheduled":
        return PROGRAMME
    return EN_COURS


def interpret_result(network_key: str, result: dict) -> tuple[str, str, str | None]:
    """Traduit un social-post-result de Post For Me en (statut, message, url)."""
    platform_data = result.get("platform_data") or {}
    url = platform_data.get("url")
    details = result.get("details") or {}
    error = result.get("error")
    if result.get("success"):
        message = "publié"
        if network_key == "tiktok":
            message += " (lien du profil TikTok : Post For Me ne renvoie pas le lien de la vidéo)"
        return PUBLIE, message, url
    if network_key == "tiktok" and (
        (isinstance(details, dict) and details.get("status") == "Processing")
        or "Still Proccessing" in json.dumps(details, ensure_ascii=False)
    ):
        return (A_VERIFIER,
                "échec déclaré par Post For Me (TikTok encore en traitement) mais la vidéo peut "
                "avoir été publiée : vérifier sur le compte TikTok", url)
    text = error if isinstance(error, str) else json.dumps(error, ensure_ascii=False) if error else ""
    if isinstance(details, dict) and details.get("error"):
        text = f"{text} — {json.dumps(details['error'], ensure_ascii=False)[:800]}".strip(" —")
    return ERREUR, text or "échec sans message de l'API", url


def subject(rep: dict) -> str:
    pack = rep.get("pack_id") or "pack inconnu"
    if rep.get("refused"):
        return f"[UDR publication] {pack} — pack refusé"
    kind = {"depot": "dépôt", "suivi": "suivi", "simulation": "simulation"}[rep["kind"]]
    mode = f" — {rep['mode']}" if rep.get("mode") else ""
    counts = ", ".join(f"{n} {s}" for s, n in rep.get("summary", {}).items()) or "aucun réseau"
    return f"[UDR publication] {pack}{mode} — {kind} : {counts}"


def render_text(rep: dict) -> str:
    lines = [subject(rep), ""]
    if rep.get("title"):
        lines.append(f"Pack : {rep['title']} ({rep['pack_id']})")
    if rep.get("mode"):
        mode = rep["mode"]
        lines.append("Mode : " + ("BROUILLON — rien n'est publié sur les réseaux" if mode == "draft"
                                  else "LIVE — posts programmés"))
    lines.append(f"Rapport généré le {rep['generated_at']} (UTC)")
    lines.append("")
    if rep.get("refused"):
        lines.append("PACK REFUSÉ — aucun réseau n'a été touché. Corrigez puis redéposez :")
        lines += [f"  - {e}" for e in rep["errors"]]
    elif rep["errors"]:
        lines += [f"Erreur : {e}" for e in rep["errors"]]
    for entry in rep["networks"]:
        lines.append(f"■ {entry['label']} : {entry['status'].upper()}")
        lines.append(f"    {entry['message']}")
        if entry.get("scheduled_at"):
            lines.append(f"    date : {entry['scheduled_at']}")
        if entry.get("pfm_post_id"):
            lines.append(f"    id Post For Me : {entry['pfm_post_id']}")
        for name, url in (entry.get("links") or {}).items():
            label = {"post_for_me": "à vérifier dans Post For Me", "video": "vidéo", "post": "post"}.get(name, name)
            lines.append(f"    {label} : {url}")
        if entry.get("api_error"):
            lines.append(f"    réponse de l'API : {entry['api_error']}")
        lines.append("")
    if rep.get("skipped"):
        lines.append("Réseaux désactivés dans le pack : " + ", ".join(rep["skipped"]))
    if rep.get("warnings"):
        lines.append("Avertissements :")
        lines += [f"  - {w}" for w in rep["warnings"]]
    return "\n".join(lines).rstrip() + "\n"
