# Note de reprise — outil de publication UDR

Branche : `claude/memoire-territoire-campaign-v6gh3v`. Pas de pull request pour l'instant.
Rédigée le 2026-09-24, en fin de session des étapes A à C. La prochaine étape est la D
(test de bout en bout en draft), dans une nouvelle session.

## Où en est-on

- **A (lecture de l'API Post For Me) : faite.** Le site et l'API étaient bloqués par le
  réseau de la session. J'ai lu le SDK Python officiel `post_for_me` 1.16.0 (généré
  depuis l'OpenAPI) et le code source public `DayMoonDevelopment/post-for-me`
  (commit a11a689, 2026-09-20). Voir « Faits établis » plus bas.
- **B (Cloudinary) et C (code) : faits.**
  - `udr_publish/` : la logique ;
  - `scripts/publish.py` : la ligne de commande ;
  - `service/` : le service Flask pour Railway ;
  - `workflows/udr-publish.json` : le workflow n8n ;
  - `schema/posts.schema.json`, `README.md`.
- **Tests** : `python -m pytest`, 43 tests verts hors réseau, avec faux Post For Me et
  faux Cloudinary. Ils couvrent la validation, l'idempotence, l'isolation des échecs,
  l'absence de secret dans le rapport et le journal, et le service HTTP.
- **Déjà vérifié sur de vrais fichiers** :
  - pack factice généré par `scripts/make_test_pack.py`, validé par ffprobe ;
  - simulation (`--dry-run`) ;
  - service lancé sous gunicorn : `/healthz`, refus sans jeton (401), rapport renvoyé.
- **Rien n'a encore été envoyé** à Post For Me ni à Cloudinary.

## Décisions de Jean (à respecter)

1. Journal : un fichier JSONL local ignoré par git (`PUBLISH_DATA_DIR/publish-log.jsonl`).
   Airtable plus tard si le besoin se confirme.
2. n8n Cloud (`fmanat.app.n8n.cloud`) : il ne peut pas exécuter de script. La logique
   tourne donc dans le service Railway, protégé par un secret partagé. Le workflow se
   réduit à : formulaire → appel HTTP au service → e-mail de rapport.
3. Date passée en live : le pack est refusé avec un message clair. On ne publie jamais
   immédiatement.
4. YouTube et TikTok sont publiés en public. TikTok : quand Post For Me déclare un échec
   alors que la vidéo a peut-être été publiée, le statut est « à vérifier ».
5. LinkedIn : le texte part **en entier** dans le texte du post (`shareCommentary`). La
   copie limitée à 200 caractères ne sert qu'à la description de la vidéo. La limite
   réelle est celle de Post For Me, 2200 caractères pour tous les réseaux (et non les
   3000 de LinkedIn). Un texte d'environ 400 caractères passe.
6. Masters : H.264, 1080×1920 ou 1920×1080, 25 i/s, AAC stéréo 128 kbit/s. Le format est
   vérifié par ffprobe et le pack est refusé sinon.
7. Jamais de mode live pendant les tests. `PUBLISH_ALLOW_LIVE` reste à 0 : tout pack
   live est alors refusé par le code.

## Faits établis (code source de Post For Me)

- **Authentification** : `Authorization: Bearer`.
- **Création** : `POST /v1/social-posts`, avec `caption`, `social_accounts`, `media[].url`,
  `account_configurations`, `scheduled_at`, `isDraft` et `external_id`.
- **Brouillon** (`isDraft`) : le post est stocké chez Post For Me et n'est jamais traité ni
  envoyé au réseau. Il n'existe donc pas de lien réseau pour un brouillon.
- **Promotion** : `PUT /v1/social-posts/{id}` supprime puis recrée le post avec le même id.
  L'API la refuse si le post est déjà traité (`processed`).
- **Idempotence** : `external_id` n'est pas unique côté API. D'où notre journal, plus une
  vérification par `GET /v1/social-posts?external_id=` en filet de sécurité.
- **Dates** : `scheduled_at` doit être dans le futur. Le planificateur passe toutes les
  2 minutes, et les résultats se lisent sur `GET /v1/social-post-results?post_id=`.
- **Vidéos** :
  - Post For Me télécharge l'URL publique et la recopie chez lui ;
  - Facebook et Instagram reçoivent une URL ; YouTube, TikTok, LinkedIn et X reçoivent le
    fichier ;
  - un fichier conforme aux masters n'est pas réencodé.
- **Textes modifiés par Post For Me** : X coupé à 280 caractères ; Instagram nettoyé
  (espaces, hashtags en double, plus de 30 hashtags ou 20 mentions) ; titre YouTube limité
  à 100 caractères, sans retour à la ligne ni `<>`. Notre validation refuse tout pack
  concerné.
- **YouTube Shorts** : pas de notion distincte. C'est un second post YouTube avec la vidéo
  verticale.

## Étape D : faite le 2026-09-24 (Railway + page /depot)

Service Railway `udr-social-production.up.railway.app`, branche
`claude/intelligent-curie-flk07e`, volume `/data`, `PUBLISH_ALLOW_LIVE=0`. Pack de test
`UDR_test_20260924_111917` déposé par la page `/depot` (Facebook seul, draft) :

- 1er dépôt : `Facebook : BROUILLON`, id Post For Me `sp_2rijdjtFIbhMGTTTMG`, vidéo
  `…/video/upload/v1790249284/udr-publish/UDR_test_20260924_111917/horizontal.mp4` ;
- 2e dépôt identique : `BROUILLON INCHANGÉ`, même id, rien renvoyé.

Incident rencontré : `Invalid Signature` de Cloudinary, dû à un `CLOUDINARY_API_SECRET`
qui ne correspondait pas à la clé ; corrigé en recopiant le secret de la même ligne de clé.

Restent : brancher n8n (nouveau `PUBLISH_SERVICE_TOKEN` aléatoire), renseigner les autres
`PFM_ACCOUNT_*`, puis un premier pack réel en draft sur tous les réseaux.

## Étape D : procédure initiale en ligne de commande (pour mémoire)

**Prérequis, côté Jean, dans l'environnement cloud** (sélecteur au-dessus de la zone de
message → engrenage) :

- **Network access** : `Custom`, en cochant la liste par défaut, avec les domaines
  `api.postforme.dev`, `api.cloudinary.com` et `res.cloudinary.com`.
- **Variables d'environnement** :
  - `POST_FOR_ME_API_KEY`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` ;
  - `PFM_ACCOUNT_FACEBOOK` ;
  - facultatif : `PFM_TEAM_ID` et `PFM_PROJECT_ID`.

  Sur Pro ou Max, la clé Post For Me peut plutôt être déclarée en *API credential* (hôte
  `api.postforme.dev`, en-tête Authorization, préfixe Bearer). Poser alors
  `PFM_AUTH_VIA_PROXY=1`.
- Ne jamais demander de clé dans le chat.

**Commandes** (depuis la racine du dépôt) :

```bash
pip install -r requirements-dev.txt && which ffprobe || apt-get install -y ffmpeg
python -m pytest -q
env | grep -c PUBLISH_ALLOW_LIVE=1   # doit afficher 0
python scripts/publish.py accounts   # vérifier l'id Facebook (aucun jeton n'est affiché)
python scripts/make_test_pack.py --id UDR_test_D1
python scripts/publish.py run packs/UDR_test_D1 --dry-run
python scripts/publish.py run packs/UDR_test_D1 --json > data/rapport_D1.json   # attendu : BROUILLON
python scripts/publish.py run packs/UDR_test_D1        # attendu : BROUILLON INCHANGÉ, aucune création
python scripts/publish.py check UDR_test_D1            # attendu : brouillon
```

**Contrôles à joindre au rapport** :

- l'URL Cloudinary contient `/v<version>/` ;
- l'id Post For Me et son statut `draft` ;
- le journal `data/publish-log.jsonl` (événements `received`, `upload`, `post`) ;
- le second dépôt ne fait aucun `POST /v1/social-posts`.

Ensuite, supprimer le brouillon de test dans Post For Me, ou le laisser : il n'est jamais
envoyé.

## Points ouverts et risques à vérifier

- **Taille des vidéos dans n8n Cloud** : le formulaire fait transiter les vidéos par n8n
  Cloud, qui limite la taille des envois selon l'offre. À tester avec un vrai master.
  Si c'est bloquant, le service pourrait servir lui-même la page de dépôt (protégée),
  n8n ne gardant que l'e-mail.
- **Nom des fichiers binaires dans n8n** : le formulaire range chaque fichier sous le
  libellé de son champ (`posts_json`, `video_vertical`, `video_horizontal`, avec
  `multipleFiles: false`). À confirmer à l'import. En cas d'écart, ajuster
  `inputDataFieldName` dans le nœud HTTP.
- **Cloudinary** :
  - vérifier la taille maximale de vidéo de l'offre ;
  - l'algorithme de signature est sha1 par défaut ; mettre
    `CLOUDINARY_SIGNATURE_ALGORITHM=sha256` si le compte l'exige.
- **TikTok** : une application non auditée chez TikTok force les posts en privé. Post For
  Me ne le gère pas ; à surveiller lors du premier post live.
- **Railway** : sans volume monté sur `/data`, le journal disparaît à chaque déploiement.
  La vérification par `external_id` évite alors les doublons, mais le volume reste
  nécessaire.
- **Suivi automatique** : `/packs/<id>/status` existe, mais aucun workflow n8n ne
  l'appelle encore. On pourrait ajouter un rappel programmé après la date de publication.
