"""Réseaux gérés, dans l'ordre de priorité de publication.

Chaque clé de `posts` dans posts.json correspond à une entrée ici. Les six
réseaux demandés sont pris en charge par Post For Me ; YouTube Shorts n'y
est pas un réseau distinct : c'est un second post sur le compte YouTube,
avec la vidéo verticale (YouTube le classe lui-même en Short).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Network:
    key: str            # clé dans posts.json
    label: str          # nom affiché dans le rapport
    platform: str       # plateforme Post For Me, et compte PFM_ACCOUNT_<PLATFORM>
    needs_title: bool = False
    supported: bool = True
    account: str = ""   # clé du compte dans ACCOUNT_ENV ; par défaut la plateforme
    placement: str = "" # placement Facebook/Instagram imposé (timeline, reels)

    @property
    def account_key(self) -> str:
        return self.account or self.platform


NETWORKS: tuple[Network, ...] = (
    Network("facebook", "Facebook", "facebook"),
    Network("instagram", "Instagram", "instagram"),
    Network("youtube", "YouTube", "youtube", needs_title=True),
    Network("youtube_shorts", "YouTube Shorts", "youtube", needs_title=True),
    Network("tiktok", "TikTok", "tiktok"),
    Network("linkedin", "LinkedIn", "linkedin"),
    Network("x", "X", "x"),
    # Page Facebook Repère Funéraire : même vidéo, deux formats.
    Network("facebook_repere", "Repère Funéraire (fil)", "facebook", account="facebook_repere",
            placement="timeline"),
    Network("facebook_repere_reel", "Repère Funéraire (Reel)", "facebook", account="facebook_repere",
            placement="reels"),
)

BY_KEY = {n.key: n for n in NETWORKS}


def account_configuration(network: Network, post: dict) -> dict:
    """Réglages propres au réseau, sans jamais toucher au texte.

    Le texte part tel quel dans `caption` ; seul le titre YouTube (fourni par
    posts.json) et les réglages de visibilité sont ajoutés ici.
    """
    if network.platform == "youtube":
        return {
            "title": post["title"],
            "privacy_status": "public",
            "made_for_kids": False,
        }
    if network.platform == "tiktok":
        return {"privacy_status": "public"}
    if network.placement:
        return {"placement": network.placement}
    if network.platform == "facebook":
        # Vidéo 16:9 publiée dans le fil (timeline). Sans placement explicite,
        # Facebook la traitait en Reel et la repartageait en Story recadrée en 9:16.
        return {"placement": "timeline"}
    if network.platform == "instagram":
        return {"placement": "reels"}
    return {}
