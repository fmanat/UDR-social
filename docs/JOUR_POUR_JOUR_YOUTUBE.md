# Jour pour jour : règles YouTube (depuis le 11/11/2026)

Décision de Jean du 11/11/2026 : comme les carnets d'avis de décès, les vidéos « Jour pour jour »
publiées sur YouTube doivent renvoyer vers le site. Page visée : **https://undernierregard.fr/hommage-televise**
(l'offre « rendre hommage à un proche à la télévision locale »).

Ces règles valent pour chaque nouveau pack `UDR_jourpourjour_…`. Les autres réseaux ne changent pas,
sauf l'adresse à l'image (point 3), qui figure dans les deux vidéos du pack.

## 1. Description : le lien en première ligne

`posts.youtube.text` et `posts.youtube_shorts.text` commencent par cette ligne, mot pour mot :

```
Le même hommage pour un proche, diffusé à la télévision locale : https://undernierregard.fr/hommage-televise
```

Puis une ligne vide, puis le texte habituel. Toujours `https://` (sans lui, YouTube ne rend pas le lien
cliquable). Terminer par une ligne de hashtags : `#jourpourjour #hommage #undernierregard`.

## 2. Mots-clés (`tags`, vidéo horizontale et Short)

Nouveau champ `tags` dans `posts.youtube` et `posts.youtube_shorts` : une liste de 8 à 15 mots-clés,
sans virgule ni `<` `>`, sans doublon, 500 caractères au plus en tout (le service refuse le pack sinon).
Dans cet ordre :

1. le nom complet (« Thierry Le Luron ») ;
2. « mort de <Nom> », « <Nom> décès », « <Nom> hommage » ;
3. « il y a <N> ans », « <jour> <mois> <année> » (date du décès) ;
4. le métier ou ce qui l'a fait connaître (« imitateur », « humoriste ») ;
5. toujours : « jour pour jour », « hommage », « un dernier regard », « hommage télévisé ».

## 3. Adresse du site visible pendant toute la vidéo

« undernierregard.fr » incrusté **du début à la fin** dans les deux vidéos du pack, même style que les
carnets YouTube : couleur dorée de la charte, petite taille (environ 34 px en 1920×1080, 40 px en
1080×1920), discret mais lisible.

- 16:9 : en bas à droite, à 48 px des bords.
- 9:16 : centré, au-dessus de la zone couverte par l'interface des Shorts, TikTok et Reels
  (rien dans les 420 px du bas ni dans les 160 px de droite).

**Ne pas toucher à la version antenne** (séquence déposée dans udr-app pour les chaînes) : l'adresse
ne s'ajoute qu'aux vidéos du pack réseaux.

## 4. Miniature de la vidéo horizontale (`thumbnail_ms`)

Nouveau champ `thumbnail_ms` dans `posts.youtube` : l'instant (en millisecondes) de la vidéo 16:9 pris
comme miniature. Choisir une image où le portrait est entièrement tracé et où le nom et les deux dates
sont lisibles (en général 1 à 2 s avant le fondu final). Vérifier l'image extraite à cet instant avant
d'envoyer le pack. Pas de `thumbnail_ms` pour `youtube_shorts` : YouTube ne prend pas de miniature
personnalisée pour un Short par cette voie.

## Exemple (extrait de posts.json)

```json
"youtube": {
  "media": "horizontal",
  "title": "Il y a quarante ans : Thierry Le Luron, 13 novembre 1986 — un dernier regard",
  "text": "Le même hommage pour un proche, diffusé à la télévision locale : https://undernierregard.fr/hommage-televise\n\nIl y a quarante ans, le 13 novembre 1986, disparaissait Thierry Le Luron. …\n\n#jourpourjour #hommage #undernierregard",
  "tags": ["Thierry Le Luron", "mort de Thierry Le Luron", "Thierry Le Luron décès", "Thierry Le Luron hommage", "il y a 40 ans", "13 novembre 1986", "imitateur", "jour pour jour", "hommage", "un dernier regard", "hommage télévisé"],
  "thumbnail_ms": 52000
},
"youtube_shorts": {
  "media": "vertical",
  "title": "Il y a quarante ans : Thierry Le Luron #Shorts",
  "text": "Le même hommage pour un proche, diffusé à la télévision locale : https://undernierregard.fr/hommage-televise\n\n13 novembre 1986. Cent voix, un seul trait.\n\n#jourpourjour #hommage #undernierregard",
  "tags": ["Thierry Le Luron", "mort de Thierry Le Luron", "il y a 40 ans", "jour pour jour", "hommage", "un dernier regard"]
}
```
