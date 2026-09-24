# Publication réseaux sociaux — Un dernier regard

Outil de LE XV PRODUCTION SAS. Un **pack de publication** contient un `posts.json`
(voir `campaigns/UDR_memoire_territoire_V1.json`) et deux vidéos. L'outil valide le
pack, héberge les vidéos sur Cloudinary, puis crée un post par réseau via l'API
[Post For Me](https://api.postforme.dev). **Déposer un pack vaut approbation** ; rien
d'autre ne déclenche une publication.

```
formulaire n8n Cloud ──► service Railway (service/app.py) ──► e-mail de rapport
                              │  même code que scripts/publish.py
                              ├─ validation : schema/posts.schema.json + règles réseau + ffprobe
                              ├─ Cloudinary : upload signé, URL versionnée renvoyée par l'API
                              ├─ Post For Me : 1 post par réseau, external_id « <pack>:<réseau> »
                              └─ journal JSONL (data/publish-log.jsonl) : idempotence
```

Réseaux, dans l'ordre : Facebook, Instagram, YouTube, YouTube Shorts (second post sur le
compte YouTube, vidéo verticale), TikTok, LinkedIn, X. Les six sont pris en charge par
Post For Me.

## Garanties

- **Brouillon par défaut** : sans `"mode": "live"`, les posts sont créés en brouillon chez
  Post For Me (`isDraft`) et **rien n'est envoyé aux réseaux**. Le mode live est en plus
  refusé tant que le serveur n'a pas `PUBLISH_ALLOW_LIVE=1`.
- **Jamais de publication immédiate** : en live, une date passée (ou à moins de
  `PUBLISH_MIN_LEAD_MINUTES`) fait refuser le pack entier.
- **Idempotence** : un réseau déjà programmé ou publié n'est jamais renvoyé. Redéposer un
  pack en brouillon met le brouillon à jour ; le redéposer en live promeut le brouillon.
  Même sans journal, un post portant déjà l'`external_id` est repris, pas recréé.
- **Isolation des échecs** : chaque réseau a son statut (brouillon, programmé, publié,
  en erreur, à vérifier, déjà envoyé) et le message de l'API.
- **Textes tels quels** : aucun ajout. Tout texte que Post For Me modifierait (X > 280,
  nettoyage Instagram, titre YouTube, > 2200 caractères…) fait refuser le pack.
- **Vidéos** : MP4 H.264, 1080×1920 (verticale) et 1920×1080 (horizontale), 25 i/s,
  AAC stéréo 128 kbit/s ; sinon le pack est refusé. Ce format évite le réencodage de
  Post For Me.
- **Secrets** : uniquement dans `.env` (ignoré par git), Railway et les credentials n8n.

## Installation (poste local)

Python 3.11+ et ffmpeg (pour `ffprobe`).

```bash
pip install -r requirements-dev.txt
cp .env.example .env        # puis remplir ; .env n'est jamais commité
python scripts/publish.py accounts   # affiche les id spc_… à reporter dans PFM_ACCOUNT_*
python -m pytest            # tests hors réseau
```

## Variables d'environnement

| Variable | Rôle |
|---|---|
| `POST_FOR_ME_API_KEY` | clé API Post For Me (secret) |
| `PFM_ACCOUNT_FACEBOOK`, `_INSTAGRAM`, `_YOUTUBE`, `_TIKTOK`, `_LINKEDIN`, `_X` | id `spc_…` des comptes connectés (YouTube sert aussi aux Shorts) |
| `PFM_TEAM_ID`, `PFM_PROJECT_ID` | facultatif : liens « à vérifier » vers app.postforme.dev |
| `CLOUDINARY_CLOUD_NAME` | `dl8itl9nw` par défaut |
| `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | identifiants Cloudinary (secrets) |
| `CLOUDINARY_FOLDER` | dossier des vidéos (`udr-publish`) |
| `PUBLISH_ALLOW_LIVE` | `0` par défaut : tout pack live est refusé |
| `PUBLISH_MIN_LEAD_MINUTES` | délai minimal avant publication (5) |
| `PUBLISH_DATA_DIR` | journal et verrous (`./data` ; Railway : `/data`, volume) |
| `PUBLISH_SERVICE_TOKEN` | secret partagé avec n8n (service HTTP) |
| `PFM_AUTH_VIA_PROXY` | `1` seulement si la clé est injectée par un proxy |

## Ligne de commande

```bash
python scripts/publish.py validate <dossier du pack>          # vérifie, n'envoie rien
python scripts/publish.py run <dossier du pack> --dry-run     # montre les requêtes
python scripts/publish.py run <dossier du pack>               # dépôt (+ --json)
python scripts/publish.py check <id du pack>                  # suivi après la date
```

Codes de sortie : 0 tout va bien, 1 au moins un réseau en erreur, 2 pack refusé.

## Service Railway et workflow n8n

1. **Railway** : nouveau service depuis ce dépôt (Dockerfile). Ajouter un **volume monté
   sur `/data`**, puis les variables ci-dessus avec `PUBLISH_ALLOW_LIVE=0`. Vérifier
   `https://<domaine>/healthz`.
2. **n8n Cloud** : importer `workflows/udr-publish.json`, puis
   - nœud *Service de publication* : remplacer l'URL par `https://<domaine>/packs` et créer
     un credential **Header Auth** : nom `Authorization`, valeur `Bearer <PUBLISH_SERVICE_TOKEN>` ;
   - nœud *Formulaire de dépôt* : créer un credential **Basic Auth** (accès au formulaire) ;
   - nœuds e-mail : choisir le credential SMTP et l'adresse d'expédition.
   Le workflow exporté ne contient aucun credential.

Suivi : `GET /packs/<id>/status` (même en-tête) renvoie le rapport de suivi.

## Tester en draft

```bash
python scripts/make_test_pack.py --id UDR_test_V1   # 2 vidéos courtes + posts.json Facebook, draft
python scripts/publish.py run packs/UDR_test_V1 --dry-run
python scripts/publish.py run packs/UDR_test_V1
```

Le rapport donne pour Facebook : `BROUILLON`, l'id Post For Me, le lien de vérification
et l'URL Cloudinary versionnée. Redéposer le même pack doit donner `BROUILLON INCHANGÉ`,
sans nouvel appel de création. Garder `PUBLISH_ALLOW_LIVE=0` pendant les tests.

## Passer en live

1. Vérifier les brouillons (liens du rapport, tableau de bord Post For Me).
2. Sur Railway, passer `PUBLISH_ALLOW_LIVE=1`.
3. Dans `posts.json`, mettre `"mode": "live"` et des dates futures, puis **redéposer le
   même pack (même id)** : chaque brouillon est promu en post programmé, sans doublon.
4. Après l'heure prévue, lancer `check` (ou `/status`) : publié, en erreur avec le message
   de l'API, ou « à vérifier » quand Post For Me déclare un échec TikTok alors que la vidéo
   a pu être publiée.

Pour modifier un post déjà programmé, le supprimer dans Post For Me puis redéposer : un
réseau déjà envoyé n'est jamais renvoyé automatiquement.
