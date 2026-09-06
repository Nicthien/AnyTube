# Lot 02 — les onze modèles de recherche restants

Lot arrêté le 6 septembre 2026, à la même révision de moteur que
[`sources-lot-01.md`](sources-lot-01.md). Les corrections du
moteur communes aux deux lots sont décrites dans le rapport du lot 01 et ne sont pas répétées ici.

## Périmètre

Les onze modèles de recherche que le lot 01 n’avait pas traités, ce qui **achève les 31 modèles de
recherche du catalogue** :

`Rokfin`, `RokfinSearch`, `Soundcloud`, `SoundcloudSearch`, `Vimeo`, `VrSquareSearch`,
`YahooSearch`, `Youtube`, `YoutubeMusicSearchURL`, `YoutubeSearch`, `YoutubeSearchURL`.

Soit six plateformes : Rokfin, SoundCloud, Vimeo, VR SQUARE, Yahoo Vidéos, YouTube.

Cela ne termine **pas** le catalogue : 1 719 extracteurs installés n’ont toujours aucun modèle de
recherche, et leur examen plateforme par plateforme reste entier.

## Trois états distincts

Comme pour le lot 01, ce rapport sépare la **disponibilité technique** (ce que l’interface
officielle ou l’extracteur installé permet), l’**implémentation** (ce que le modèle envoie) et la
**vérification** (ce qu’un essai daté a observé). Un essai de recherche ne vérifie jamais la
lecture, l’audio, le direct, les sous-titres ni le téléchargement : ces cinq fonctions restent
**non vérifiées** pour la totalité du lot.

## Corrections apportées

### 1. VR SQUARE : une recherche qui marche, un catalogue qu’on ne peut pas lire

Le modèle était classé « aucun résultat ». Deux causes distinctes, aucune n’étant une panne :

- la requête d’essai était inadaptée. `livr.jp` est un catalogue japonais de vidéos VR ; la requête
  `nature` n’y correspond à rien. Avec `VR` ou `ライブ`, l’API `/ajax/web-search` répond bien et
  renvoie des contenus ;
- les entrées renvoyées ne portent que des URL. Le worker les ré-extrayait une par une, chaque
  extraction échouait sur « VR SQUARE app-only videos are not supported », et **les entrées étaient
  abandonnées en silence** — d’où le « vide » trompeur.

`home_query` passe donc à `VR`, et le worker remonte désormais la cause réelle
(`unsupported_media`, correction 11 du lot 01) au lieu d’une liste vide.

Formulé exactement : **la recherche du fournisseur répond**, et **le modèle ne peut produire aucun
résultat**, parce que VR SQUARE réserve ces vidéos à son application. Le tableau ci-dessous porte
donc « média non lisible · 0/3 requêtes » : ce n’est ni une réussite, ni une panne, ni un résultat
vide. Aucun contournement n’a été tenté.

### 2. YouTube : un seul classement de recherche réellement disponible

Le classement « Plus vues » était câblé sur le préfixe `ytsearch` et n’existait donc pas pour
`YoutubeSearchURL`. Il est désormais déclaré (`search_views_url`) et disponible pour `Youtube`,
`YoutubeSearch` et `YoutubeSearchURL`.

Un classement « Nouveautés » a été **essayé puis retiré** : les codes de filtre `sp=CAISAhAB` et
`sp=CAI%3D` renvoient exactement les mêmes trois premiers résultats que la recherche par défaut
(`BHACKCNDMW8`, `SYyvx6GE2UI`, `znnSGHMnCzo` le 6 septembre 2026), alors que `sp=CAMSAhAB` change
bien l’ordre. Proposer ce classement aurait affiché un tri qui ne trie pas ; il n’est pas offert.

`YoutubeMusicSearchURL` reste sans classement : `music.youtube.com` n’utilise pas les mêmes filtres.

### 3. Un accueil bâti sur une requête ne peut plus se présenter comme un flux (`app/connectors.py`)

Le lot 01 avait introduit `home_kind` pour nommer une recherche servie en accueil, mais l’étiquette
restait **déclarée à la main** — et Vimeo, dont l’accueil est
`api.vimeo.com/videos?query={query}`, était bel et bien annoncé « Flux d’accueil ».

L’étiquette est désormais **déduite** : à la validation du connecteur, toute URL d’accueil qui
contient `{query}` force `home_kind='search'`. C’est une correction, pas un refus : une source déjà
enregistrée qui déclarait `feed` est corrigée à la lecture, elle n’est pas rejetée. Un test parcourt
les 31 modèles et vérifie qu’aucun ne peut présenter une recherche comme un flux de la plateforme.

### 4. Vimeo : les tris documentés sont déclarés, l’accès reste à fournir

`search_views_url` et `search_recent_url` reprennent les paramètres `sort=plays` et `sort=date`
documentés par l’API Vimeo, en miroir des flux d’accueil déjà présents. **Implémenté, non
vérifié** : sans jeton d’accès l’API répond 401, et aucun jeton n’est demandé ni écrit ici.

## Résultat par modèle

Les preuves complètes sont dans `docs/source-audit-lot-02/` (un fichier JSON par modèle, plus
`summary.json`), au même format et à la même révision que celles du lot 01.

Environnement : `local-main`, Windows-11-10.0.26200-SP0, Python 3.14.6, yt-dlp 2026.08.19, révision du moteur de connecteurs `90864eb5adce6b21`, sondage du 2026-09-06T18:25:10 UTC. Proxy de sortie configuré : non.

Chaque recherche est essayée avec trois requêtes adaptées à la plateforme, sur deux pages de trois résultats. Un modèle est déclaré au meilleur état observé : une requête en échec ne le condamne pas, et une requête qui répond ne masque pas les autres — le détail par requête figure dans les preuves.

| Modèle | Interface réellement utilisée | Recherche (3 requêtes × 2 pages) | Accueil | Classements |
| --- | --- | --- | --- | --- |
| `Rokfin` | yt-dlp `rkfnsearch` (identifiants extraits des scripts rokfin.com) | panne temporaire · 0/3 requêtes · 0 URL distinctes, 0 répétées | panne temporaire · servi par recherche « vidéos » | aucun classement disponible |
| `RokfinSearch` | yt-dlp `rkfnsearch` (identifiants extraits des scripts rokfin.com) | panne temporaire · 0/3 requêtes · 0 URL distinctes, 0 répétées | panne temporaire · servi par recherche « vidéos » | aucun classement disponible |
| `Soundcloud` | yt-dlp `scsearch` (API SoundCloud) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par recherche « vidéos » | aucun classement disponible |
| `SoundcloudSearch` | yt-dlp `scsearch` (API SoundCloud) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par recherche « vidéos » | aucun classement disponible |
| `Vimeo` | API Vimeo (JSON officiel) — jeton d’accès requis | authentification requise · 0/3 requêtes · 0 URL distinctes, 0 répétées | authentification requise · servi par flux | `home:views` : authentification requise<br>`home:recent` : authentification requise<br>`search:views` : authentification requise<br>`search:recent` : authentification requise |
| `VrSquareSearch` | yt-dlp `VrSquareSearch` (ajax livr.jp) | média non lisible · 0/3 requêtes · 0 URL distinctes, 0 répétées | média non lisible · servi par recherche « VR » | aucun classement disponible |
| `YahooSearch` | yt-dlp `yvsearch` (API JSON Yahoo Vidéos) | panne temporaire · 0/3 requêtes · 0 URL distinctes, 0 répétées | panne temporaire · servi par recherche « vidéos » | aucun classement disponible |
| `Youtube` | yt-dlp `ytsearch` | résultats reçus · 3/3 requêtes · 17 URL distinctes, 1 répétées | résultats reçus · servi par recherche « vidéos » | `home:views` : résultats reçus<br>`search:views` : résultats reçus |
| `YoutubeMusicSearchURL` | yt-dlp sur `music.youtube.com/search` | résultats reçus · 3/3 requêtes · 15 URL distinctes, 3 répétées | résultats reçus · servi par recherche « vidéos » | aucun classement disponible |
| `YoutubeSearch` | yt-dlp `ytsearch` | résultats reçus · 3/3 requêtes · 15 URL distinctes, 3 répétées | résultats reçus · servi par recherche « vidéos » | `home:views` : résultats reçus<br>`search:views` : résultats reçus |
| `YoutubeSearchURL` | yt-dlp sur `youtube.com/results` (filtre vidéo) | résultats reçus · 3/3 requêtes · 17 URL distinctes, 1 répétées | résultats reçus · servi par recherche « vidéos » | `home:views` : résultats reçus<br>`search:views` : résultats reçus |

Remarques par modèle :

- `Rokfin` — Extracteur amont cassé : les identifiants de recherche ne sont plus à l’emplacement attendu sur rokfin.com.
- `RokfinSearch` — Voir `Rokfin` : même extracteur, même panne amont.
- `Vimeo` — API Vimeo en 401 ; jeton d’accès requis, aucun n’était disponible pour l’essai.
- `VrSquareSearch` — La recherche répond avec une requête adaptée au catalogue japonais ; les vidéos sont réservées à l’application du fournisseur et ne sont pas lisibles.
- `YahooSearch` — Extracteur amont cassé : l’API JSON appelée ne renvoie plus de JSON. Aucune API sans clé pour la remplacer.

Révisions de modèle effectivement testées :

- `Rokfin` : `fc82a747a1b29e39aadff96957e17cbd…`
- `RokfinSearch` : `fc82a747a1b29e39aadff96957e17cbd…`
- `Soundcloud` : `c7d28dd0be07f6012ba33246234d1266…`
- `SoundcloudSearch` : `c7d28dd0be07f6012ba33246234d1266…`
- `Vimeo` : `177a509fdb0e17b88d0c745cf43204ec…`
- `VrSquareSearch` : `03d1d5e2fa5f964698e27ec8c567d358…`
- `YahooSearch` : `24bee9c137c2531148c832a737729430…`
- `Youtube` : `f841bf70b56ad6c81663780824ad8413…`
- `YoutubeMusicSearchURL` : `f0b7e2b0b8320155c3bc37d8988a86ce…`
- `YoutubeSearch` : `f841bf70b56ad6c81663780824ad8413…`
- `YoutubeSearchURL` : `8b36a034b9401b22c1d98d2729518c15…`

## Ce qui reste à faire

1. **Rokfin (2 modèles)** — l’extracteur installé récupère ses identifiants de recherche en lisant
   les scripts `/static/js/*` de `rokfin.com/discover`. Vérifié le 6 septembre 2026 : cette page
   répond 404 et ne référence plus aucun script à cet emplacement, donc `self._db_url` reste vide et
   l’appel de recherche échoue en 404. Le site lui-même répond 200. **Panne d’extracteur amont**,
   ni une absence de compte ni une indisponibilité de la plateforme. Aucune API de recherche
   publique n’a été trouvée pour la remplacer ; non corrigé.
2. **YahooSearch** — l’extracteur appelle
   `video.search.yahoo.com/search/?…&o=js`, qui ne renvoie plus de JSON : 500 avec l’en-tête de
   yt-dlp, page HTML avec un en-tête de navigateur. **Panne d’extracteur amont**, sans interface
   publique sans clé pour la remplacer ; non corrigé. Même situation que `GoogleSearch` au lot 01.
3. **Vimeo** — le connecteur accepte un jeton du coffre, mais **rien n’a pu être essayé** : ni la
   recherche, ni les deux classements, ni la pagination par page. Le format des résultats provient
   de la documentation de l’API, pas d’une réponse observée.
4. **VR SQUARE** — la lecture est impossible par conception (contenu réservé à l’application). Le
   modèle reste utile pour parcourir le catalogue, jamais pour lire. Aucun contournement n’a été
   tenté et aucun ne doit l’être.
5. **SoundCloud** — la recherche répond, mais l’extracteur n’expose aucun tri et l’API publique
   demande un `client_id` pour un flux d’accueil : ni classement ni accueil réel. Non développé.
6. **YouTube** — pas de tri par date exploitable (voir correction 2) ; l’accueil reste une recherche
   sur `home_query`, explicitement nommée comme telle. Les filtres de durée et de date ne sont
   toujours disponibles que sur Dailymotion.
7. **Pagination par préfixe** — les neuf modèles yt-dlp de ce lot relancent la recherche complète à
   chaque page. Les répétitions mesurées figurent dans le tableau ci-dessus.
8. **`capabilities()['home_kind']`** — ce champ informatif de `/api/sources` est calculé sur la
   configuration telle qu’elle est stockée, sans passer par la correction d’étiquette du
   validateur : une source enregistrée avant ce lot peut donc encore y annoncer `feed`. Le libellé
   réellement affiché au lecteur vient de `/api/home` (`feed_kind`) et est correct. À unifier au
   prochain lot.
9. **Noms affichés** — `BiliBiliSearch` et `DailymotionSearch` s’affichent encore avec le nom brut
   de leur extracteur (`BiliBiliSearch`, `dailymotion:search`) faute d’entrée dans la table des
   noms revus. Purement cosmétique ; corrigé au prochain lot, car toucher `catalog.py` change la
   révision du moteur et périmerait les preuves de ces deux lots.
10. **Toutes plateformes** — lecture, audio, direct, sous-titres et téléchargement restent **non
   vérifiés**. Aucune recette navigateur, Docker ou Unraid n’a été exécutée sur cette branche.

## Fichiers modifiés

Les fichiers du moteur sont ceux du lot 01 ; ce lot y ajoute :

| Fichier | Nature |
| --- | --- |
| `app/connectors.py` | Étiquette d’accueil déduite du modèle ; VR SQUARE (`home_query`), YouTube (`search_views_url`), Vimeo (`search_*_url`) |
| `app/catalog.py` | Noms revus des onze modèles, table `LIMITATIONS` |
| `scripts/audit_lot.py` | Lot 02, requêtes adaptées, option `--batch` |
| `tests/test_lot02.py` | Tests de contrat déterministes du lot |
| `docs/sources-lot-02.md` | Ce rapport |
| `docs/source-audit-lot-02/` | Preuves réseau datées |

## Comment rejouer les preuves

```
python scripts/audit_lot.py --batch lot-02
python scripts/audit_lot.py --batch lot-02 --update-checks
```

## Validation exécutée

- `python -m unittest discover -s tests` — **85 tests, tous verts**, dans `.venv` du projet.
- `git diff --check` — sans avertissement.
- Garde-fou des dialogues natifs — inclus dans la série.
- Les essais réseau restent hors de `tests/` : aucun test déterministe n’ouvre de connexion.
