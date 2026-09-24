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


NETWORKS: tuple[Network, ...] = (
    Network("facebook", "Facebook", "facebook"),
    Network("instagram", "Instagram", "instagram"),
    Network("youtube", "YouTube", "youtube", needs_title=True),
    Network("youtube_shorts", "YouTube Shorts", "youtube", needs_title=True),
    Network("tiktok", "TikTok", "tiktok"),
    Network("linkedin", "LinkedIn", "linkedin"),
    Network("x", "X", "x"),
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
    return {}
