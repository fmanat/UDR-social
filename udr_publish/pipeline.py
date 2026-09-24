"""Orchestration : pack → validation → Cloudinary → Post For Me → journal → rapport.

Règles clés :
- un post Post For Me par réseau, `external_id` = « <id du pack>:<réseau> » ;
- un réseau déjà programmé ou publié n'est jamais renvoyé ;
- un brouillon existant est mis à jour (mode draft) ou promu (mode live) ;
- l'échec d'un réseau n'interrompt pas les autres ;
- les textes partent tels quels (aucun ajout).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import report as R
from .cloudinary_client import CloudinaryClient, CloudinaryError
from .journal import Journal
from .networks import BY_KEY, account_configuration
from .postforme import PostForMeClient, PostForMeError
from .settings import Settings
from .validate import NetworkPlan, ValidatedPack, validate_pack

SENT_STATUSES = {"scheduled", "processing", "processed"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def external_id(pack_id: str, network_key: str) -> str:
    return f"{pack_id}:{network_key}"


def build_payload(pack: ValidatedPack, plan: NetworkPlan, account_id: str, media_url: str) -> dict:
    payload: dict = {
        "caption": plan.post["text"],          # tel quel
        "social_accounts": [account_id],
        "media": [{"url": media_url}],
        "external_id": external_id(pack.pack_id, plan.network.key),
        "isDraft": pack.mode == "draft",
    }
    config = account_configuration(plan.network, plan.post)
    if config:
        payload["account_configurations"] = [{"social_account_id": account_id, "configuration": config}]
    if plan.scheduled_at is not None:
        payload["scheduled_at"] = plan.scheduled_at.isoformat()
    return payload


def payload_hash(payload: dict) -> str:
    content = {k: v for k, v in payload.items() if k != "isDraft"}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Publisher:
    def __init__(self, settings: Settings, session=None, pfm: PostForMeClient | None = None,
                 cloud: CloudinaryClient | None = None):
        self.settings = settings
        self.session = session or requests.Session()
        self.journal = Journal(settings.journal_path, settings.locks_dir)
        self._pfm = pfm
        self._cloud = cloud

    @property
    def pfm(self) -> PostForMeClient:
        if self._pfm is None:
            s = self.settings
            self._pfm = PostForMeClient(self.session, s.pfm_base_url, s.pfm_api_key, s.pfm_auth_via_proxy)
        return self._pfm

    @property
    def cloud(self) -> CloudinaryClient:
        if self._cloud is None:
            s = self.settings
            self._cloud = CloudinaryClient(self.session, s.cloudinary_cloud_name, s.cloudinary_api_key,
                                           s.cloudinary_api_secret, s.cloudinary_signature_algorithm)
        return self._cloud

    # ------------------------------------------------------------------ dépôt
    def run(self, directory: Path, now: datetime | None = None, dry_run: bool = False) -> dict:
        now = now or datetime.now(timezone.utc)
        validation = validate_pack(directory, self.settings, now=now)
        if not validation.ok:
            rep = R.refused_report(validation.pack_id, validation.errors, validation.warnings)
            if validation.pack_id and R.valid_pack_id(validation.pack_id):
                self.journal.append(validation.pack_id, "refused", errors=validation.errors)
            return rep
        pack = validation.pack
        assert pack is not None
        rep = R.new_report(pack, validation.warnings, dry_run)
        if dry_run:
            for plan in pack.plans:
                account = self.settings.pfm_accounts.get(plan.network.platform) or "<compte non configuré>"
                payload = build_payload(pack, plan, account, f"<url Cloudinary de la vidéo {plan.media_slot}>")
                R.add_network(rep, plan.network, R.SIMULATION, "rien n'a été envoyé", payload=payload,
                              scheduled_at=payload.get("scheduled_at"))
            return R.finalize(rep)

        with self.journal.lock(pack.pack_id):
            self.journal.append(pack.pack_id, "received", mode=pack.mode,
                                posts_sha256=sha256_file(directory / "posts.json"),
                                networks=[p.network.key for p in pack.plans])
            state = self.journal.network_state(pack.pack_id)

            # Réseaux déjà envoyés en live ou sans compte : rien à faire, pas même un upload.
            todo: list[NetworkPlan] = []
            for plan in pack.plans:
                known = state.get(plan.network.key)
                if not self.settings.pfm_accounts.get(plan.network.platform):
                    var = f"PFM_ACCOUNT_{plan.network.platform.upper()}"
                    R.add_network(rep, plan.network, R.ERREUR, f"compte {plan.network.label} non configuré ({var})")
                    self.journal.append(pack.pack_id, "error", network=plan.network.key, stage="config",
                                        message=f"{var} absent")
                elif known and known.get("status") in SENT_STATUSES:
                    # Confirmé auprès de Post For Me : un post supprimé à la main peut être renvoyé.
                    try:
                        current = self.pfm.get_post(known["pfm_post_id"])
                    except PostForMeError as exc:
                        if exc.status == 404:
                            self.journal.append(pack.pack_id, "post_missing", network=plan.network.key,
                                                pfm_post_id=known["pfm_post_id"])
                            state[plan.network.key] = None
                            todo.append(plan)
                        else:
                            R.add_network(rep, plan.network, R.ERREUR, self.settings.redact(
                                f"statut du post existant invérifiable, rien renvoyé : {exc}"),
                                pfm_post_id=known["pfm_post_id"])
                        continue
                    except requests.RequestException as exc:
                        R.add_network(rep, plan.network, R.ERREUR, self.settings.redact(
                            f"Post For Me injoignable, rien renvoyé : {exc}"), pfm_post_id=known["pfm_post_id"])
                        continue
                    if current.status in SENT_STATUSES:
                        R.add_network(rep, plan.network, R.DEJA_ENVOYE,
                                      f"déjà envoyé (statut {current.status}) le {known['ts']} — aucun renvoi",
                                      pfm_post_id=current.id, scheduled_at=current.scheduled_at,
                                      links=self._links(current.id, known.get("media_url")))
                    else:
                        todo.append(plan)
                else:
                    todo.append(plan)

            media_urls, media_errors = self._upload_media(pack, {p.media_slot for p in todo})
            rep["media"] = media_urls

            for plan in todo:
                self._publish_network(rep, pack, plan, state.get(plan.network.key),
                                      media_urls.get(plan.media_slot, {}).get("url"),
                                      media_errors.get(plan.media_slot))
        return R.finalize(rep)

    def _upload_media(self, pack: ValidatedPack, slots: set[str]) -> tuple[dict, dict]:
        urls: dict[str, dict] = {}
        errors: dict[str, str] = {}
        done = self.journal.uploads(pack.pack_id)
        for slot in sorted(slots):
            path = pack.media_files[slot]
            digest = sha256_file(path)
            previous = done.get((slot, digest))
            if previous:
                urls[slot] = {"url": previous["secure_url"], "reused": True, "file": path.name}
                continue
            public_id = f"{self.settings.cloudinary_folder}/{pack.pack_id}/{slot}"
            try:
                result = self.cloud.upload_video(path, public_id)
            except (CloudinaryError, requests.RequestException) as exc:
                errors[slot] = self.settings.redact(f"upload Cloudinary échoué : {exc}")
                self.journal.append(pack.pack_id, "error", stage="upload", slot=slot, message=errors[slot])
                continue
            self.journal.append(pack.pack_id, "upload", slot=slot, sha256=digest, file=path.name,
                                secure_url=result.secure_url, version=result.version,
                                public_id=result.public_id, bytes=result.bytes)
            urls[slot] = {"url": result.secure_url, "reused": False, "file": path.name}
        return urls, errors

    def _publish_network(self, rep: dict, pack: ValidatedPack, plan: NetworkPlan, known: dict | None,
                         media_url: str | None, media_error: str | None) -> None:
        network = plan.network
        account_id = self.settings.pfm_accounts[network.platform]
        if not media_url:
            R.add_network(rep, network, R.ERREUR, media_error or "vidéo indisponible")
            return

        payload = build_payload(pack, plan, account_id, media_url)
        digest = payload_hash(payload)
        ext = payload["external_id"]
        try:
            if known is None:
                known = self._adopt(pack.pack_id, network.key, ext)
            if known is not None:
                try:
                    current = self.pfm.get_post(known["pfm_post_id"])
                except PostForMeError as exc:
                    if exc.status != 404:
                        raise
                    self.journal.append(pack.pack_id, "post_missing", network=network.key,
                                        pfm_post_id=known["pfm_post_id"])
                    known, current = None, None
            if known is not None and current is not None:
                if current.status in SENT_STATUSES:
                    self._record(pack, network.key, "observed", current, digest, media_url)
                    R.add_network(rep, network, R.DEJA_ENVOYE,
                                  f"déjà envoyé (statut {current.status}) — aucun renvoi",
                                  pfm_post_id=current.id, scheduled_at=current.scheduled_at,
                                  links=self._links(current.id, media_url))
                    return
                if pack.mode == "draft" and known.get("payload_hash") == digest:
                    R.add_network(rep, network, R.BROUILLON_INCHANGE,
                                  "brouillon déjà créé avec ce contenu — rien renvoyé",
                                  pfm_post_id=current.id, scheduled_at=current.scheduled_at,
                                  links=self._links(current.id, media_url))
                    return
                result = self.pfm.update_post(current.id, payload)
                action = "promoted" if pack.mode == "live" else "updated"
            else:
                result = self.pfm.create_post(payload)
                action = "created"
        except PostForMeError as exc:
            message = self.settings.redact(str(exc))
            self.journal.append(pack.pack_id, "error", network=network.key, stage="postforme",
                                http_status=exc.status, message=message)
            R.add_network(rep, network, R.ERREUR, message, api_error=self.settings.redact(exc.body or ""),
                          links=self._links(None, media_url))
            return
        except requests.RequestException as exc:
            message = self.settings.redact(f"Post For Me injoignable : {exc}")
            self.journal.append(pack.pack_id, "error", network=network.key, stage="postforme", message=message)
            R.add_network(rep, network, R.ERREUR, message, links=self._links(None, media_url))
            return

        self._record(pack, network.key, action, result, digest, media_url)
        status = R.status_from_api(result.status, action)
        message = {
            "created": "brouillon créé chez Post For Me — rien n'est envoyé au réseau"
            if result.status == "draft" else f"programmé pour {result.scheduled_at}",
            "updated": "brouillon mis à jour avec le nouveau contenu",
            "promoted": f"brouillon passé en live, programmé pour {result.scheduled_at}",
        }[action]
        if result.status not in ("draft", "scheduled"):
            message = f"statut inattendu renvoyé par Post For Me : {result.status}"
        R.add_network(rep, network, status, message, pfm_post_id=result.id,
                      scheduled_at=result.scheduled_at, links=self._links(result.id, media_url))

    def _adopt(self, pack_id: str, network_key: str, ext: str) -> dict | None:
        """Filet de sécurité : un post portant déjà cet external_id est repris, pas recréé."""
        found = self.pfm.find_by_external_id(ext)
        if not found:
            return None
        post = found[0]
        return self.journal.append(pack_id, "post", network=network_key, action="adopted",
                                   pfm_post_id=post.id, status=post.status,
                                   scheduled_at=post.scheduled_at, external_id=ext, payload_hash=None)

    def _record(self, pack: ValidatedPack, network_key: str, action: str, post, digest: str,
                media_url: str) -> None:
        self.journal.append(pack.pack_id, "post", network=network_key, action=action, mode=pack.mode,
                            pfm_post_id=post.id, status=post.status, scheduled_at=post.scheduled_at,
                            external_id=external_id(pack.pack_id, network_key), payload_hash=digest,
                            media_url=media_url)

    def _links(self, pfm_post_id: str | None, media_url: str | None, post_url: str | None = None) -> dict:
        links = {}
        if pfm_post_id and self.settings.dashboard_url(pfm_post_id):
            links["post_for_me"] = self.settings.dashboard_url(pfm_post_id)
        if media_url:
            links["video"] = media_url
        if post_url:
            links["post"] = post_url
        return links

    # ----------------------------------------------------------------- suivi
    def check(self, pack_id: str) -> dict:
        """Interroge Post For Me pour chaque réseau du pack et met le journal à jour."""
        state = self.journal.network_state(pack_id)
        rep = R.status_report(pack_id)
        if not state:
            rep["errors"].append("aucun envoi journalisé pour ce pack")
            return R.finalize(rep)
        for key in [k for k in BY_KEY if k in state]:
            network = BY_KEY[key]
            known = state[key]
            post_id = known["pfm_post_id"]
            media_url = known.get("media_url")
            try:
                post = self.pfm.get_post(post_id)
                results = self.pfm.post_results(post_id) if post.status == "processed" else []
            except (PostForMeError, requests.RequestException) as exc:
                R.add_network(rep, network, R.ERREUR, self.settings.redact(f"suivi impossible : {exc}"),
                              pfm_post_id=post_id, links=self._links(post_id, media_url))
                continue
            if post.status != "processed":
                status = {"draft": R.BROUILLON, "scheduled": R.PROGRAMME}.get(post.status, R.EN_COURS)
                R.add_network(rep, network, status, f"statut Post For Me : {post.status}",
                              pfm_post_id=post_id, scheduled_at=post.scheduled_at,
                              links=self._links(post_id, media_url))
                continue
            if not results:
                R.add_network(rep, network, R.EN_COURS, "traité, résultat pas encore disponible",
                              pfm_post_id=post_id, links=self._links(post_id, media_url))
                continue
            for result in results:
                status, message, url = R.interpret_result(network.key, result)
                self.journal.append(pack_id, "result", network=key, pfm_post_id=post_id, status=status,
                                    success=result.get("success"), url=url, message=message)
                R.add_network(rep, network, status, message, pfm_post_id=post_id,
                              api_error=_short(result.get("error")),
                              links=self._links(post_id, media_url, url))
        return R.finalize(rep)


def _short(value) -> str:
    if value in (None, "", {}):
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text[:1000]
