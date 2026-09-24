"""Règles de texte : garantir que Post For Me enverra le texte tel quel.

Post For Me modifie silencieusement certains textes (troncature, nettoyage).
Plutôt que de laisser faire, on refuse tout pack dont un texte serait
modifié. Les règles ci-dessous reproduisent le code source de Post For Me
(github.com/DayMoonDevelopment/post-for-me, commit a11a689) :

- API : `caption.length <= 2200` pour toutes les plateformes
  (api/src/social-posts/social-posts.service.ts, validatePostCaptionLength) ;
- X : `caption.slice(0, 280)` (twitter-post-client.ts) ;
- Instagram : #sanitizeCaption (instagram-post-client.ts) ;
- YouTube : #sanitizeYouTubeCaption (titre) et #sanitizeYouTubeDescription.

Les longueurs sont comptées comme en JavaScript : en unités UTF-16.
"""

from __future__ import annotations

import re

CAPTION_MAX = 2200
X_MAX = 280
YOUTUBE_TITLE_MAX = 100
YOUTUBE_DESCRIPTION_MAX_BYTES = 5000  # limite de l'API YouTube (snippet.description)
INSTAGRAM_MAX_HASHTAGS = 30
INSTAGRAM_MAX_MENTIONS = 20

# \w de JavaScript (sans drapeau u) = [A-Za-z0-9_]
_IG_HASHTAG = re.compile(r"#[A-Za-z0-9_À-ſ-]+")
_IG_MENTION = re.compile(r"@[A-Za-z0-9_À-ſ.-]+")


def js_len(text: str) -> int:
    """Longueur d'une chaîne JavaScript (unités UTF-16)."""
    return len(text.encode("utf-16-le")) // 2


def _js_trim(text: str) -> str:
    return text.strip()


def _ig_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text


def instagram_problems(text: str) -> list[str]:
    """Raisons pour lesquelles Instagram (via Post For Me) modifierait le texte."""
    problems: list[str] = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _js_trim(_ig_whitespace(normalized))
    if normalized != text:
        problems.append(
            "espaces ou retours à la ligne qui seraient normalisés "
            "(espaces multiples, tabulations, espaces en début/fin de ligne ou de texte, \\r)"
        )
    hashtags = [m.group(0).lower() for m in _IG_HASHTAG.finditer(normalized)]
    duplicates = sorted({h for h in hashtags if hashtags.count(h) > 1})
    if duplicates:
        problems.append("hashtags en double, qui seraient supprimés : " + ", ".join(duplicates))
    if len(set(hashtags)) > INSTAGRAM_MAX_HASHTAGS:
        problems.append(f"plus de {INSTAGRAM_MAX_HASHTAGS} hashtags ({len(set(hashtags))}) : l'excédent serait supprimé")
    mentions = _IG_MENTION.findall(normalized)
    if len(mentions) > INSTAGRAM_MAX_MENTIONS:
        problems.append(f"plus de {INSTAGRAM_MAX_MENTIONS} mentions ({len(mentions)}) : l'excédent serait supprimé")
    if re.search(r"\n{3,}", normalized):
        problems.append("plus de deux retours à la ligne consécutifs, qui seraient réduits à deux")
    return problems


def text_problems(network_key: str, text: str, title: str | None = None) -> list[str]:
    """Liste des problèmes bloquants pour le texte (et le titre) d'un réseau."""
    problems: list[str] = []
    length = js_len(text)
    if not text.strip():
        problems.append("texte vide")
    if length > CAPTION_MAX:
        problems.append(f"texte de {length} caractères : Post For Me refuse au-delà de {CAPTION_MAX}")

    if network_key == "x" and length > X_MAX:
        problems.append(f"texte de {length} caractères : X le couperait à {X_MAX}")

    if network_key == "instagram":
        problems.extend(instagram_problems(text))

    if network_key in ("youtube", "youtube_shorts"):
        if title is None or not title.strip():
            problems.append("titre YouTube manquant")
        else:
            if re.search(r"[<>]", title):
                problems.append("titre YouTube : les caractères < et > seraient supprimés")
            if "\n" in title or "\r" in title:
                problems.append("titre YouTube : les retours à la ligne seraient remplacés par des espaces")
            if title != title.strip():
                problems.append("titre YouTube : espaces en début ou fin, qui seraient supprimés")
            if js_len(title) > YOUTUBE_TITLE_MAX:
                problems.append(f"titre YouTube de {js_len(title)} caractères : coupé à {YOUTUBE_TITLE_MAX}")
        if re.search(r"[<>]", text):
            problems.append("description YouTube : les caractères < et > seraient supprimés")
        if text != text.strip():
            problems.append("description YouTube : espaces en début ou fin, qui seraient supprimés")
        size = len(text.encode("utf-8"))
        if size > YOUTUBE_DESCRIPTION_MAX_BYTES:
            problems.append(f"description YouTube de {size} octets : YouTube refuse au-delà de {YOUTUBE_DESCRIPTION_MAX_BYTES}")
    return problems


_PLACEHOLDER = re.compile(r"\[[^\]\n]{2,80}\]")


def text_warnings(text: str) -> list[str]:
    """Avertissements non bloquants (ex. espace réservé oublié)."""
    found = _PLACEHOLDER.findall(text)
    if found:
        return ["le texte semble contenir un espace réservé : " + ", ".join(found)]
    return []
