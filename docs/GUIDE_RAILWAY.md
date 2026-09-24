# Mettre le service en ligne sur Railway et faire le test en brouillon

Ce guide ne demande **aucun terminal**. Tout se fait dans le navigateur.
Comptez 30 à 45 minutes la première fois.

Ce qu'il faut avoir sous la main :

- un compte **Railway** (railway.com) relié à votre compte GitHub ;
- un accès à **Post For Me** (app.postforme.dev) avec la page Facebook déjà connectée ;
- un accès à **Cloudinary** (console.cloudinary.com) ;
- un gestionnaire de mots de passe (celui du navigateur suffit) pour inventer deux secrets.

> **Règle d'or pendant tout le test** : la variable `PUBLISH_ALLOW_LIVE` reste à `0`.
> Tant qu'elle vaut `0`, le service refuse toute publication réelle, quoi qu'il arrive.

Les écrans de Railway changent parfois de libellé. Si un bouton porte un nom un peu
différent, cherchez celui qui s'en approche le plus.

---

## Partie 1 — Créer le service sur Railway

**1. Ouvrir Railway.** Allez sur **railway.com** et connectez-vous.
*Vous devez voir* votre tableau de bord, avec la liste de vos projets (vide si c'est le
premier).

**2. Créer un projet.** Cliquez sur **New Project** (ou **+ New**), puis sur
**Deploy from GitHub repo**.
*Vous devez voir* la liste de vos dépôts GitHub.
Si **UDR-social** n'apparaît pas, cliquez sur **Configure GitHub App**. Autorisez Railway
à voir ce dépôt, puis revenez.

**3. Choisir le dépôt.** Cliquez sur **fmanat/UDR-social**. S'il vous propose
**Deploy Now** ou **Add variables**, choisissez **Deploy Now** : les variables viendront
après.
*Vous devez voir* un canevas (fond quadrillé) avec une carte « UDR-social ». Un premier
déploiement démarre sur la branche principale. **Il échouera ou restera incomplet, c'est
normal** : la bonne branche et les variables ne sont pas encore réglées.

**4. Choisir la bonne branche.** Cliquez sur la carte **UDR-social**. Un panneau s'ouvre
à droite. Allez dans l'onglet **Settings**, section **Source**, ligne **Branch**
(branche). Choisissez **`claude/intelligent-curie-flk07e`**.
*Vous devez voir* le nom de la branche affiché dans la section Source.

> Pourquoi cette branche et non `claude/memoire-territoire-campaign-v6gh3v` ? Elle
> contient tout le travail de la branche `…v6gh3v`, **plus** la page de dépôt décrite en
> partie 4. Si vous préférez rester sur `…v6gh3v`, il faudra d'abord y fusionner cette
> branche, sinon la page n'existera pas.

**5. Vérifier la configuration.** Dans le même onglet **Settings**, section **Build**,
vous devez voir **Dockerfile** comme méthode de construction. Railway le lit tout seul
dans le fichier `railway.json` du dépôt : il n'y a rien à changer.

---

## Partie 2 — Ajouter le volume sur /data

Le volume est un petit disque qui survit aux redéploiements. Le service y garde son
journal, qui l'empêche d'envoyer deux fois le même post.

**6. Créer le volume.** Revenez sur le canevas (cliquez en dehors du panneau). Faites un
**clic droit sur la carte UDR-social**, puis choisissez **Attach volume** (ou
**Add Volume**).
Autre chemin : bouton **+ Create** (ou **+ New**) en haut du canevas, puis **Volume**,
puis choisissez le service **UDR-social**.

**7. Indiquer le chemin.** Railway demande un **Mount path** (chemin de montage).
Tapez exactement :

```
/data
```

puis validez.
*Vous devez voir* sur le canevas une petite carte de volume, collée sous la carte
UDR-social et marquée `/data`.

---

## Partie 3 — Saisir les variables d'environnement

**8. Ouvrir les variables.** Cliquez sur la carte **UDR-social**, puis sur l'onglet
**Variables**.
*Vous devez voir* une liste vide, ou quelques variables de Railway, et un bouton
**+ New Variable**.

**9. Méthode pour chaque variable.** Pour chacune des lignes du tableau ci-dessous :

1. cliquez sur **+ New Variable** ;
2. dans la première case (**VARIABLE_NAME**), collez le **nom** exact, en majuscules ;
3. dans la seconde case (**VALUE**), collez la **valeur** ;
4. cliquez sur **Add** (ou la coche).

*Vous devez voir* la variable s'ajouter à la liste. Sa valeur est masquée par des
étoiles, c'est normal.

Ne mettez **ni espace ni guillemets** autour des valeurs.

### Variables à saisir maintenant

| # | Nom | Valeur | Où la trouver |
|---|---|---|---|
| a | `PUBLISH_ALLOW_LIVE` | `0` | Tapez `0`. C'est le verrou anti-publication. |
| b | `PUBLISH_DATA_DIR` | `/data` | Tapez `/data`, le chemin du volume de l'étape 7. |
| c | `PUBLISH_MIN_LEAD_MINUTES` | `5` | Tapez `5`. |
| d | `PUBLISH_PAGE_PASSWORD` | un mot de passe de **12 caractères minimum** | Inventez-le avec votre gestionnaire de mots de passe et gardez-le : il ouvre la page de dépôt. |
| e | `PUBLISH_SERVICE_TOKEN` | un secret long (40 caractères, lettres et chiffres) | Inventez-le de la même façon. Il servira à n8n plus tard. Il doit être **différent** du mot de passe (d). |
| f | `POST_FOR_ME_API_KEY` | la clé API Post For Me | Sur **app.postforme.dev**, ouvrez votre projet, puis la rubrique des **clés API** (*API Keys*). Copiez la clé existante ou créez-en une. |
| g | `CLOUDINARY_CLOUD_NAME` | `dl8itl9nw` | Sur **console.cloudinary.com**, le *Cloud name* est affiché en haut du tableau de bord. |
| h | `CLOUDINARY_API_KEY` | une suite de chiffres | Sur **console.cloudinary.com** : roue dentée **Settings**, puis **API Keys**. Colonne **API Key**. |
| i | `CLOUDINARY_API_SECRET` | une suite de lettres et chiffres | Même écran, colonne **API Secret**. Cliquez sur l'œil pour l'afficher, puis copiez. |
| j | `CLOUDINARY_FOLDER` | `udr-publish` | Tapez `udr-publish`. |
| k | `PFM_TEAM_ID` | facultatif | Sur app.postforme.dev, ouvrez votre projet et regardez l'adresse : `app.postforme.dev/`**équipe**`/`**projet**`/…`. Le premier morceau est l'équipe. |
| l | `PFM_PROJECT_ID` | facultatif | Le second morceau de la même adresse. |
| m | `PORT` | `8080` | Tapez `8080`. C'est le port où le service écoute ; il resservira à l'étape 12. |

`PFM_ACCOUNT_FACEBOOK` viendra à l'étape 16 : le service vous donnera lui-même la valeur.
Ne créez pas `PFM_AUTH_VIA_PROXY` : elle ne sert pas sur Railway.

**10. Appliquer les changements.** Railway accumule les modifications sans les appliquer.
En haut du canevas, un bandeau indique par exemple *« 13 changes »*, avec un bouton
**Deploy** (ou **Apply changes**). Cliquez dessus.
*Vous devez voir* la carte UDR-social passer à **Building** (construction), puis à
**Deploying**. La première construction prend 3 à 5 minutes, le temps d'installer ffmpeg.

**11. Attendre le vert.** Ouvrez l'onglet **Deployments** du service.
*Vous devez voir* le dernier déploiement marqué **Success** ou **Active**, en vert.
S'il est rouge (**Failed** ou **Crashed**), cliquez dessus, puis sur **View logs**.
Copiez les dernières lignes et envoyez-les-moi.

---

## Partie 4 — Vérifier que le service répond

**12. Créer l'adresse publique.** Service **UDR-social**, onglet **Settings**, section
**Networking**, puis **Generate Domain**. Si Railway demande un port (*Target port*), tapez
`8080`, comme la variable `PORT` (ligne m).
*Vous devez voir* une adresse du type `udr-social-production-xxxx.up.railway.app`.
C'est **votre domaine** ; il servira dans toutes les étapes suivantes.

**13. Tester la santé du service.** Dans un nouvel onglet du navigateur, ouvrez :

```
https://<votre domaine>/healthz
```

*Vous devez voir* une seule ligne de texte :

```
{"live_enabled":false,"ok":true}
```

- `"ok":true` : le service tourne.
- `"live_enabled":false` : le verrou anti-publication est bien en place.

**Si vous lisez `"live_enabled":true`, arrêtez-vous** : remettez `PUBLISH_ALLOW_LIVE`
à `0`, puis cliquez sur Deploy.

Si la page ne s'affiche pas (*Application failed to respond*), attendez une minute et
rechargez. Si le problème persiste, reprenez l'étape 11.

**14. Ouvrir la page de dépôt.** Ouvrez :

```
https://<votre domaine>/depot
```

*Vous devez voir* une petite fenêtre du navigateur qui demande un nom d'utilisateur et un
mot de passe.

- **Nom d'utilisateur** : ce que vous voulez, par exemple `jean`.
- **Mot de passe** : celui de la variable `PUBLISH_PAGE_PASSWORD` (étape 9, ligne d).

*Vous devez voir* ensuite la page « **Dépôt d'un pack de publication** », avec trois
cadres en pointillés (posts.json, vidéo verticale, vidéo horizontale) et un bouton bleu
grisé **Déposer et approuver**.

Si vous lisez à la place *« Page de dépôt désactivée »*, le mot de passe est absent ou
fait moins de 12 caractères : corrigez la variable, puis cliquez sur Deploy.

**15. Afficher les comptes Post For Me.** En bas de la page, cliquez sur le lien
**Comptes connectés chez Post For Me**.
*Vous devez voir* une liste de ce type :

```
facebook     spc_XXXXXXXXXXXXXXXXXXXX        Un dernier regard (connected)
             → PFM_ACCOUNT_FACEBOOK
```

Si vous lisez *« Lecture impossible… HTTP 401 »*, la clé Post For Me (ligne f) est
fausse ou incomplète. Recopiez-la.

**16. Poser l'id Facebook.** Copiez l'id `spc_…` de la ligne **facebook**. Dans Railway,
onglet **Variables**, ajoutez :

| Nom | Valeur |
|---|---|
| `PFM_ACCOUNT_FACEBOOK` | l'id `spc_…` copié |

Faites de même pour les autres réseaux si vous le souhaitez (`PFM_ACCOUNT_INSTAGRAM`,
`PFM_ACCOUNT_YOUTUBE`, `PFM_ACCOUNT_TIKTOK`, `PFM_ACCOUNT_LINKEDIN`, `PFM_ACCOUNT_X`).
Le test n'utilise que Facebook.
Cliquez sur **Deploy** et attendez le vert (étape 11).
*Vous devez voir*, en rechargeant la page des comptes, la mention
**« → PFM_ACCOUNT_FACEBOOK : déjà en place »**.

---

## Partie 5 — Déposer le pack de test en brouillon

Deux chemins sont possibles. **Le chemin A (page du service) est le plus simple** : il
ne dépend pas de n8n et affiche le rapport directement à l'écran.

### Chemin A — par la page du service (recommandé)

**17. Télécharger le pack de test.** Sur `https://<votre domaine>/depot`, cliquez sur
**télécharger un pack de test**. Attendez environ 10 secondes.
*Vous devez voir* un fichier `UDR_test_AAAAMMJJ_HHMMSS.zip` (quelques Mo) arriver dans
vos téléchargements.
Ce pack contient :

- un `posts.json` limité à Facebook, en mode **draft** (brouillon), avec une date dans
  30 jours ;
- deux vidéos factices de 3 secondes, marquées « TEST UDR – NE PAS PUBLIER ».

**18. Décompresser.**

- **Windows** : clic droit sur le fichier, puis **Extraire tout**.
- **Mac** : double-clic.

*Vous devez voir* un dossier `UDR_test_…` contenant trois fichiers : `posts.json`,
`…_9x16.mp4` et `…_16x9.mp4`.

**19. Glisser les fichiers.** Faites glisser chaque fichier dans son cadre, ou cliquez
dans le cadre pour le choisir :

- `posts.json` dans le cadre **1** ;
- le fichier qui finit par **`_9x16.mp4`** dans le cadre **2** (vidéo verticale) ;
- le fichier qui finit par **`_16x9.mp4`** dans le cadre **3** (vidéo horizontale).

*Vous devez voir* :

- les trois cadres passer en **trait vert plein**, avec le nom et la taille de chaque
  fichier ;
- sous le cadre 1, une pastille verte **BROUILLON**, suivie de
  « Pack UDR_test_… — réseaux : facebook » ;
- le bouton **Déposer et approuver** devenir bleu vif.

**Si la pastille est rouge et indique « LIVE »**, ne cliquez pas : ce n'est pas le pack de
test.

**20. Déposer.** Cliquez sur **Déposer et approuver**.
*Vous devez voir* une barre de progression (« Envoi des fichiers… 45 % »), puis le
message « Fichiers reçus. Vérification, Cloudinary puis Post For Me… ». Au bout de
quelques secondes à une minute, le message devient **« Terminé. Rapport ci-dessous. »**
en vert, avec un rapport de ce type :

```
[UDR publication] UDR_test_… — draft — dépôt : 1 brouillon

Pack : Pack de test — ne pas publier (UDR_test_…)
Mode : BROUILLON — rien n'est publié sur les réseaux
…
■ Facebook : BROUILLON
    …
    id Post For Me : sp_…
    à vérifier dans Post For Me : https://app.postforme.dev/…
    vidéo : https://res.cloudinary.com/dl8itl9nw/video/upload/v17…/…
```

Points à vérifier dans ce rapport :

- **BROUILLON** à côté de Facebook ;
- un **id Post For Me** qui commence par `sp_` ;
- une adresse vidéo Cloudinary qui contient **`/v`** suivi de chiffres (la version).

Faites une capture d'écran du rapport et envoyez-la-moi.

**21. Redéposer à l'identique.** Sans recharger la page, cliquez de nouveau sur
**Déposer et approuver**, avec **les mêmes fichiers**. Ne téléchargez pas de nouveau pack
de test : il aurait un autre nom et compterait comme un pack différent.
*Vous devez voir* **Facebook : BROUILLON INCHANGÉ**. C'est la preuve qu'aucun doublon
n'est créé.

**22. Contrôler chez Post For Me.** Ouvrez le lien « à vérifier dans Post For Me » du
rapport, ou le tableau de bord de app.postforme.dev.
*Vous devez voir* **un seul** post, au statut **Draft**, avec le texte « TEST —
brouillon de vérification… ».
Ce brouillon n'est jamais envoyé à Facebook. Vous pouvez le supprimer ou le laisser.

**En cas de message rouge ou orange** :

- **« Pack refusé »** : le rapport liste la raison, et rien n'a été envoyé.
- **« Facebook : EN ERREUR »** : le rapport donne la réponse de Post For Me ou de
  Cloudinary. Souvent, c'est une clé mal recopiée (lignes f, h ou i) ou
  `PFM_ACCOUNT_FACEBOOK` absent.
- **« Erreur 401 »** : le mot de passe de la page a changé. Rechargez la page.

Dans tous les cas, envoyez-moi le texte du rapport. Un nouveau dépôt du même pack est
toujours sans risque.

### Chemin B — par le formulaire n8n

À utiliser plus tard, pour garder le rapport par e-mail. Réglages décrits dans le
`README.md`, section « Service Railway et workflow n8n » :

1. importer `workflows/udr-publish.json` dans n8n Cloud ;
2. dans le nœud *Service de publication*, remplacer l'adresse par
   `https://<votre domaine>/packs` ;
3. créer un credential **Header Auth** : nom `Authorization`, valeur `Bearer ` suivi de
   la valeur de `PUBLISH_SERVICE_TOKEN` (une espace après Bearer) ;
4. régler le credential **Basic Auth** du formulaire et le credential SMTP des e-mails ;
5. ouvrir l'adresse du formulaire et y déposer les trois mêmes fichiers.

*Vous devez voir* le message « Pack reçu », puis recevoir un e-mail contenant le même
rapport qu'au chemin A.

n8n Cloud limite la taille des fichiers envoyés. Avec de vrais masters de plusieurs
centaines de Mo, le chemin A est plus sûr.

---

## Rappels de sécurité

- Les clés ne se saisissent que dans Railway (onglet Variables). Jamais dans un e-mail,
  un chat ou un fichier du dépôt.
- Tant que `PUBLISH_ALLOW_LIVE` vaut `0` et que `/healthz` affiche
  `"live_enabled":false`, aucun post ne peut partir sur un réseau.
- La page `/depot` est protégée par `PUBLISH_PAGE_PASSWORD`. Pour la fermer, supprimez
  cette variable puis cliquez sur Deploy.
