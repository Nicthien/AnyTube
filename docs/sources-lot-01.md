# Lot 01 — vingt modèles de recherche

Lot arrêté le 6 septembre 2026 sur la branche `codex/sources-lot-01`, dans un checkout séparé
(`C:\DEV\Projects\AnyTube-lot01`), à partir du commit `5a225fb`.

## Périmètre

Les vingt premiers **modèles de recherche existants**, triés par identifiant, parmi les 31 que le
catalogue expose. Le tri est celui des points de code Python, donc `PRXSeries` précède `PeerTube`.

`ArchiveOrg`, `BiliBili`, `BiliBiliSearch`, `Dailymotion`, `DailymotionSearch`, `GameJolt`,
`GameJoltSearch`, `GoogleSearch`, `MailRuMusicSearch`, `Niconico`, `NicovideoSearch`,
`NicovideoSearchDate`, `NicovideoSearchURL`, `PRXSeries`, `PRXSeriesSearch`, `PRXStoriesSearch`,
`PRXStory`, `PeerTube`, `PeerTubePlaylist`, `RedGifsSearch`.

Soit dix plateformes : archive.org, Bilibili, Dailymotion, Game Jolt, Google Vidéos, Mail.ru
Musique, Niconico, PRX, PeerTube (instance Framatube), RedGifs.

Les onze modèles restants (`Rokfin`, `RokfinSearch`, `Soundcloud`, `SoundcloudSearch`, `Vimeo`,
`VrSquareSearch`, `YahooSearch`, `Youtube`, `YoutubeMusicSearchURL`, `YoutubeSearch`,
`YoutubeSearchURL`) **ne font pas partie de ce lot** et restent dans l’état antérieur.

## Trois états distincts

Ce rapport sépare volontairement :

- **disponibilité technique** — ce que l’interface officielle ou l’extracteur yt-dlp installé
  permet réellement, après lecture du code et de la documentation ;
- **implémentation** — ce que le modèle AnyTube déclare et envoie ;
- **vérification** — ce qu’un essai réseau daté a effectivement observé.

Un essai de recherche ne vérifie jamais la lecture, l’audio, le direct, les sous-titres ni le
téléchargement. Ces cinq fonctions sont explicitement listées dans chaque preuve sous
`does_not_verify` et restent **non vérifiées** pour la totalité du lot.

## Corrections apportées

### 1. Erreurs HTTP de yt-dlp jamais reconnues (`app/failures.py`)

`classify` ne testait que `urllib.error.HTTPError`. yt-dlp lève sa propre classe
`yt_dlp.networking.exceptions.HTTPError`, qui n’en hérite pas : **toute** réponse 401 ou 429
provenant d’un extracteur était rapportée comme « plateforme indisponible ». Les quatre modèles PRX
étaient donc présentés comme une panne alors que l’API PRX répond 401.

`classify` lit maintenant les deux classes, applique `Retry-After` aux 429, traite 401 comme
`authentication_required`, et ne traite un 403 comme un problème de compte que si le message du
fournisseur le dit explicitement (`LOGIN_MARKERS`). Un 403 seul reste `temporarily_unavailable`.

### 2. Recherche Niconico cassée en amont (`app/connectors.py`)

`nicosearch`, `nicosearchdate` et `NicovideoSearchURL` extraient `data-video-id` du HTML de
`nicovideo.jp/search`. Vérifié le 6 septembre 2026 : la page répond bien 200 sur 114 033 octets mais
ne contient **aucune** occurrence de `data-video-id` ni de lien `/watch/`. Les quatre modèles
renvoyaient donc zéro résultat, en silence.

Les quatre modèles passent sur l’**API officielle Snapshot Search v2**
(`snapshot.search.nicovideo.jp/api/v2/snapshot/video/contents/search`), en connecteur JSON
déclaratif : pagination native `_offset`, tri `_sort`, `_context=AnyTube` comme le demande la
documentation, URL de vidéo reconstruite depuis `contentId`.

- `NicovideoSearchDate` conserve sa sémantique amont (`_sort=-startTime`, le plus récent d’abord) ;
  les trois autres trient par `-viewCounter`. L’API n’expose **pas** de tri par pertinence.
- Le nom de chaîne n’est pas exposé par cette API : le champ reste vide, ce n’est pas une perte de
  données côté AnyTube.
- Plafond `_offset + _limit = 1600` documenté par le fournisseur, déclaré dans le modèle.

### 3. Paramètre vide supprimé par la pagination native (`app/connectors.py`, `app/pagination.py`, `app/main.py`)

En pagination native, `search_json` reconstruit la chaîne de requête avec
`parse_qsl(...)`, qui **supprime silencieusement les paramètres vides**. Le flux d’accueil Niconico
repose sur un `q=` vide ; il recevait donc un 400. Les trois reconstructions d’URL du projet
(`connectors.search_json`, `pagination.search_config`, `main.home_source`) utilisent désormais
`keep_blank_values=True`. Ce défaut touchait tout modèle, présent ou personnalisé, comportant un
paramètre volontairement vide.

### 4. Résultats Game Jolt perdus par une publication sans média (`app/worker.py`)

La recherche Game Jolt liste des publications communautaires ; `_parse_post` lève
« No video formats found! » dès qu’une publication n’a pas de média, ce qui faisait échouer la page
entière. yt-dlp lui-même utilise `ignore_no_formats_error` dans ses propres tests de cette classe.

Les modes **listing** (`search`, `collection`) activent `ignore_no_formats_error` : un listing n’a
jamais besoin de formats lisibles. Le mode `media` ne l’active pas — une préparation sans format
compatible échoue toujours (test `test_media_preparation_still_refuses_sources_without_formats`).

### 5. Résultats Mail.ru tous rattachés à la même URL (`app/connectors.py`, `app/worker.py`)

Les entrées de `MailRuMusicSearch` portent un identifiant distinct mais héritent de l’URL de la page
de recherche comme `webpage_url`. Toutes les cartes pointaient vers la même adresse ; la
déduplication de `/api/search` réduisait la page à un seul résultat et aucune carte ne menait à une
piste.

Nouveau champ déclaratif `item_url` (connecteurs yt-dlp uniquement, équivalent de `video_url` côté
JSON) : `https://my.mail.ru/music/songs/track-{id}`. Vérifié que `MailRuMusicIE` accepte cette forme
et renvoie la bonne piste. Le champ est validé comme les autres modèles d’URL : HTTP(S) publique,
domaine fixe, port standard, variable `{id}` seule.

### 6. Classements de recherche déclaratifs (`app/connectors.py`, `app/pagination.py`)

Les classements de recherche étaient déduits du nom d’hôte (`api.dailymotion.com`) ou du préfixe
(`ytsearch`). Trois champs déclaratifs — `search_trending_url`, `search_views_url`,
`search_recent_url` — permettent désormais à n’importe quel modèle d’exposer ses tris réels.

Les deux chemins hérités Dailymotion et YouTube sont **conservés tels quels**, y compris pour les
sources déjà enregistrées sans ces champs (`test_saved_sources_without_the_new_fields_keep_their_capabilities`).

Nouveaux classements de recherche : archive.org (`downloads`, `publicdate`, `week`), Niconico
(`-viewCounter`, `-startTime`), PeerTube (`-views`, `-publishedAt`), RedGifs (`order=top`,
`latest`, `trending`). La recherche PeerTube par défaut passe à `sort=-match`, le tri de pertinence
documenté de l’API.

### 7. Une recherche servie en accueil doit se nommer ainsi (`app/connectors.py`, `app/main.py`)

`/api/home/{id}` affichait « Flux d’accueil » dès qu’une URL d’accueil existait, même quand cette
URL est une page de résultats construite sur `home_query`. Nouveau champ `home_kind`
(`feed` par défaut, donc sans effet sur les configurations existantes) et nouveau champ de réponse
`feed_kind`.

- `home_kind='feed'` : Dailymotion, archive.org, PeerTube, Niconico — listes publiées par la
  plateforme, sans requête texte.
- `home_kind='search'` : YouTube, dont le classement « Plus vues » est une page de résultats. Le
  libellé devient « Plus vues · recherche : vidéos ».
- Accueil sans URL : libellé « Recherche : … », comme auparavant, et `feed_kind='search'`.

Le classement Niconico d’accueil interroge l’API de recherche avec un `q` **vide** et
`targets=tagsExact` : c’est un listing de tout le corpus trié, pas une requête du lecteur, d’où
`home_kind='feed'`. Ce comportement du `q` vide est **observé, non documenté** ; à revérifier au
prochain lot.

### 8. Plafond de fenêtre du fournisseur (`app/connectors.py`, `app/pagination.py`, `app/main.py`)

`Pagination.maximum_results` (0 = pas de limite annoncée) borne la pagination native. Sans lui, la
pagination Niconico dépassait la fenêtre de 1 600 résultats et l’API répondait 400 au lecteur.
`/api/search` et `/api/home` cessent d’émettre un curseur au-delà du plafond.

### 9. Le filtrage anti-robot de Bilibili passait pour une panne (`app/failures.py`)

Bilibili répond **HTTP 412 Precondition Failed** à des recherches consécutives depuis la même
adresse. Reproduit le 6 septembre 2026 : la première requête passe, les suivantes reçoivent 412 ;
`BiliBili` et `BiliBiliSearch` ont des modèles **strictement identiques** et ne différaient que par
l’instant de l’essai.

AnyTube n’émet jamais d’en-tête de requête conditionnelle — le relais média n’envoie que `Range`,
sans `If-Range` — donc un 412 venant d’un fournisseur ne peut pas répondre à une précondition que
nous aurions posée. Il est désormais classé `rate_limited` : le lecteur lit « la plateforme limite
les requêtes », et le refroidissement par plateforme de `run_worker` s’applique au lieu de relancer
aussitôt.

## Résultat par modèle

Les preuves complètes sont dans `docs/source-audit-lot-01/` (un fichier JSON par modèle, plus
`summary.json`), chacune datée et portant l’environnement, la version de Python, la version de
yt-dlp, la révision du moteur de connecteurs et la révision du modèle testé.

Environnement : `local-worktree-lot01`, Windows-11-10.0.26200-SP0, Python 3.14.6, yt-dlp 2026.08.19, révision du moteur de connecteurs `d311cba0679f3f9d`, sondage du 2026-09-06T17:26:01 UTC. Proxy de sortie configuré : non.

Chaque recherche est essayée avec trois requêtes adaptées à la plateforme, sur deux pages de trois résultats. Un modèle est déclaré au meilleur état observé : une requête en échec ne condamne pas le modèle, et une requête qui répond ne masque pas les autres — le détail par requête est dans les preuves.

| Modèle | Interface réellement utilisée | Recherche (3 requêtes × 2 pages) | Accueil | Classements |
| --- | --- | --- | --- | --- |
| `ArchiveOrg` | API `archive.org/advancedsearch.php` (JSON officiel) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par flux | `home:trending` : résultats reçus<br>`home:views` : résultats reçus<br>`home:recent` : résultats reçus<br>`search:views` : résultats reçus<br>`search:recent` : résultats reçus<br>`search:trending` : résultats reçus |
| `BiliBili` | yt-dlp `bilisearch` | résultats reçus · 2/3 requêtes · 10 URL distinctes, 2 répétées | quota atteint · servi par recherche « vidéos » | aucun classement disponible |
| `BiliBiliSearch` | yt-dlp `bilisearch` | résultats reçus · 1/3 requêtes · 5 URL distinctes, 1 répétées | quota atteint · servi par recherche « vidéos » | aucun classement disponible |
| `Dailymotion` | API Graph `api.dailymotion.com` (JSON officiel) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par flux | `home:trending` : résultats reçus<br>`home:views` : résultats reçus<br>`home:recent` : résultats reçus<br>`search:views` : résultats reçus<br>`search:recent` : résultats reçus<br>`search:trending` : résultats reçus |
| `DailymotionSearch` | API Graph `api.dailymotion.com` (JSON officiel) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par flux | `home:trending` : résultats reçus<br>`home:views` : résultats reçus<br>`home:recent` : résultats reçus<br>`search:views` : résultats reçus<br>`search:recent` : résultats reçus<br>`search:trending` : résultats reçus |
| `GameJolt` | yt-dlp `GameJoltSearch` (site-api Game Jolt) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par recherche « vidéos » | aucun classement disponible |
| `GameJoltSearch` | yt-dlp `GameJoltSearch` (site-api Game Jolt) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par recherche « vidéos » | aucun classement disponible |
| `GoogleSearch` | yt-dlp `gvsearch` (extraction HTML google.com) | réponse vide · 0/3 requêtes · 0 URL distinctes, 0 répétées | réponse vide · servi par recherche « vidéos » | aucun classement disponible |
| `MailRuMusicSearch` | yt-dlp `MailRuMusicSearch` (ajax my.mail.ru) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par recherche « vidéos » | aucun classement disponible |
| `Niconico` | API Snapshot Search v2 (JSON officiel) — **remplace** l’extraction HTML | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par flux | `home:views` : résultats reçus<br>`home:recent` : résultats reçus<br>`search:views` : résultats reçus<br>`search:recent` : résultats reçus |
| `NicovideoSearch` | API Snapshot Search v2 (JSON officiel) — **remplace** l’extraction HTML | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par flux | `home:views` : résultats reçus<br>`home:recent` : résultats reçus<br>`search:views` : résultats reçus<br>`search:recent` : résultats reçus |
| `NicovideoSearchDate` | API Snapshot Search v2, `_sort=-startTime` — **remplace** l’extraction HTML | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par flux | `home:views` : résultats reçus<br>`home:recent` : résultats reçus<br>`search:views` : résultats reçus<br>`search:recent` : résultats reçus |
| `NicovideoSearchURL` | API Snapshot Search v2 (JSON officiel) — **remplace** l’extraction HTML | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par flux | `home:views` : résultats reçus<br>`home:recent` : résultats reçus<br>`search:views` : résultats reçus<br>`search:recent` : résultats reçus |
| `PRXSeries` | yt-dlp `prxseries` (`cms.prx.org/api/v1`) | authentification requise · 0/3 requêtes · 0 URL distinctes, 0 répétées | authentification requise · servi par recherche « vidéos » | aucun classement disponible |
| `PRXSeriesSearch` | yt-dlp `prxseries` (`cms.prx.org/api/v1`) | authentification requise · 0/3 requêtes · 0 URL distinctes, 0 répétées | authentification requise · servi par recherche « vidéos » | aucun classement disponible |
| `PRXStoriesSearch` | yt-dlp `prxstories` (`cms.prx.org/api/v1`) | authentification requise · 0/3 requêtes · 0 URL distinctes, 0 répétées | authentification requise · servi par recherche « vidéos » | aucun classement disponible |
| `PRXStory` | yt-dlp `prxstories` (`cms.prx.org/api/v1`) | authentification requise · 0/3 requêtes · 0 URL distinctes, 0 répétées | authentification requise · servi par recherche « vidéos » | aucun classement disponible |
| `PeerTube` | API PeerTube v1 sur Framatube (JSON officiel) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par flux | `home:trending` : résultats reçus<br>`home:views` : résultats reçus<br>`home:recent` : résultats reçus<br>`search:views` : résultats reçus<br>`search:recent` : résultats reçus |
| `PeerTubePlaylist` | API PeerTube v1 sur Framatube — **modèle identique à `PeerTube`** | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par flux | `home:trending` : résultats reçus<br>`home:views` : résultats reçus<br>`home:recent` : résultats reçus<br>`search:views` : résultats reçus<br>`search:recent` : résultats reçus |
| `RedGifsSearch` | yt-dlp `RedGifsSearch` (API RedGifs v2) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par recherche « vidéos » | `search:views` : résultats reçus<br>`search:recent` : résultats reçus<br>`search:trending` : résultats reçus |

Remarques par modèle :

- `BiliBili` / `BiliBiliSearch` — modèles identiques ; 2/3 et 1/3 requêtes servies sur ce sondage, les autres arrêtées par le filtrage anti-robot (412, désormais rapporté comme quota). L’accueil des deux modèles a été refusé pour la même raison : **ce n’est pas un verdict**, il faut réessayer espacé.
- `BiliBili` / `BiliBiliSearch` — la deuxième page répète 1 à 2 résultats sur 3. La pagination par préfixe relance la recherche entière à chaque page ; l’ordre de Bilibili bouge entre deux appels. `/api/search` déduplique par URL, donc le lecteur voit moins de résultats neufs, jamais de doublon.
- `GameJolt` — Les publications sans média sont désormais listées au lieu de faire échouer la page.
- `GameJoltSearch` — Les publications sans média sont désormais listées au lieu de faire échouer la page.
- `GoogleSearch` — Extracteur amont cassé : le marqueur HTML recherché n’existe plus. Aucune correction possible sans clé d’API.
- `MailRuMusicSearch` — URL par piste reconstruite ; sans cela toutes les cartes partageaient l’URL de la recherche.
- `PRXSeries` — API PRX en 401 sur toutes les requêtes ; accès par compte non implémenté.
- `PRXSeriesSearch` — API PRX en 401 sur toutes les requêtes ; accès par compte non implémenté.
- `PRXStoriesSearch` — API PRX en 401 sur toutes les requêtes ; accès par compte non implémenté.
- `PRXStory` — API PRX en 401 sur toutes les requêtes ; accès par compte non implémenté.
- `PeerTubePlaylist` — Recherche de listes de lecture non implémentée ; le modèle sert la recherche vidéo.

Révisions de modèle effectivement testées :

- `ArchiveOrg` : `739e7fd14d2dc1b2cbbb0e41cc3e83e4…`
- `BiliBili` : `3e3d1434f182ec2c08e52f029b00631c…`
- `BiliBiliSearch` : `3e3d1434f182ec2c08e52f029b00631c…`
- `Dailymotion` : `be845253e45e28f6516de9043b91a550…`
- `DailymotionSearch` : `be845253e45e28f6516de9043b91a550…`
- `GameJolt` : `189c581d757185d61f53c5495beff24b…`
- `GameJoltSearch` : `189c581d757185d61f53c5495beff24b…`
- `GoogleSearch` : `ba6728c6cceeed532b09835a0e6e46e2…`
- `MailRuMusicSearch` : `df8a1b328b4ef1defc8ae7ec8db5341c…`
- `Niconico` : `f8db9c7230411ecc4597f5bf22e7eb3b…`
- `NicovideoSearch` : `f8db9c7230411ecc4597f5bf22e7eb3b…`
- `NicovideoSearchDate` : `82ba5f2965b15496508d16ea30cb6622…`
- `NicovideoSearchURL` : `f8db9c7230411ecc4597f5bf22e7eb3b…`
- `PRXSeries` : `a7077ab001c33e6a5c1c9c02eab6193e…`
- `PRXSeriesSearch` : `a7077ab001c33e6a5c1c9c02eab6193e…`
- `PRXStoriesSearch` : `c4c0594d1991a5f0c547a7b6637d0765…`
- `PRXStory` : `c4c0594d1991a5f0c547a7b6637d0765…`
- `PeerTube` : `fce800dfeaea42d7cce4ac79f15a298d…`
- `PeerTubePlaylist` : `fce800dfeaea42d7cce4ac79f15a298d…`
- `RedGifsSearch` : `5ef170a964176fcf35c58aa4a4d0da14…`

## Ce qui reste à faire

1. **PRX (4 modèles)** — `cms.prx.org/api/v1` répond 401 sur `stories/search`, `series/search` et
   sur une histoire isolée ; la racine `/api/v1` reste publique. Il s’agit d’une **authentification
   requise**, pas d’une panne ni d’une impossibilité. Il manque l’authentification par plateforme
   (jeton PRX déposé dans le coffre, aucun secret en clair) : cela dépend du chantier
   « authentification spécifique par plateforme » déjà ouvert dans `SOURCES-PROGRESS.md`.
2. **GoogleSearch** — `gvsearch` extrait `class="dXiKIc"` de `google.com/search` ; ce marqueur
   n’existe plus, l’extracteur renvoie zéro entrée sans erreur. Aucune API vidéo Google publique
   sans clé n’est disponible ; l’API Programmable Search demande une clé, donc un accès de coffre
   du même type que Vimeo. **Résultat vide constaté, cause identifiée en amont, correction non
   faite.**
3. **BiliBili / BiliBiliSearch** — les deux modèles sont **identiques octet pour octet** ; leurs
   écarts de résultat viennent uniquement du filtrage anti-robot de Bilibili (412 après la première
   requête). Ce n’est ni une panne définitive ni une réussite complète. Il manque un espacement
   volontaire entre deux recherches Bilibili successives ; le refroidissement actuel ne s’applique
   qu’après le premier refus.
   Aucun classement n’est disponible : `BiliBiliSearchIE._search_results` fixe en dur
   `order`, `duration` et `tids` dans son appel à `api.bilibili.com/x/web-interface/search/type`,
   et aucun extracteur d’URL de recherche Bilibili n’est installé — il n’existe donc pas de chemin
   déclaratif pour exposer les tris que l’API accepte pourtant.
4. **PeerTubePlaylist** — son rôle inféré est « collection » mais son modèle est aujourd’hui la
   recherche vidéo de `PeerTube`, à l’identique. L’API PeerTube expose
   `search/video-playlists` ; l’exploiter suppose de relier les résultats au navigateur de
   collections plutôt qu’à la lecture. **Non fait**, hors périmètre de ce lot.
5. **Mail.ru** — la reconstruction d’URL est vérifiée, mais Mail.ru Musique ne sert que de l’audio
   MP3. La lecture et le téléchargement depuis ce modèle **n’ont pas été essayés**.
6. **Game Jolt** — la recherche renvoie des publications communautaires ; certaines ne contiennent
   aucun média. Filtrer sur la présence de média demanderait une extraction complète par entrée,
   coûteuse et non déclarative. **Limitation documentée, non corrigée.**
7. **archive.org** — la requête est injectée dans une expression Lucene
   (`mediatype:movies AND ({query})`). Une requête contenant une parenthèse déséquilibrée a été
   essayée et le service a répondu 200, mais aucune protection explicite n’a été ajoutée.
8. **Niconico** — pas de tri par pertinence dans l’API ; pas de nom de chaîne ; classement officiel
   `nvapi.nicovideo.jp` non exploité car il exige un en-tête `X-Frontend-Id` que le modèle
   déclaratif ne peut pas porter.
9. **Pagination par préfixe** — pour toute source sans pagination native, la page suivante relance
   la recherche complète. Mesuré sur Bilibili : 1 à 2 résultats sur 3 se répètent en page 2. Les
   dix modèles JSON du lot (archive.org, Dailymotion, Niconico, PeerTube) utilisent une pagination
   native et n’ont montré **aucune** répétition sur 18 URL par modèle.
10. **Accueil des sources sans flux** — `home_query` vaut « vidéos » pour toutes les sources sans
   flux publié. Sur Game Jolt, Mail.ru et RedGifs, cela revient à chercher un mot français ; les
   trois ont malgré tout renvoyé des résultats, mais la pertinence n’est pas évaluée. Le champ est
   modifiable par le lecteur dans Mes sources ; aucun choix éditorial n’a été imposé.
11. **Toutes plateformes** — lecture, audio, direct, sous-titres et téléchargement restent **non
   vérifiés** pour ce lot. Aucune recette navigateur, aucune recette Docker et aucune recette
   Unraid n’a été exécutée sur cette branche.

## Fichiers modifiés

| Fichier | Nature |
| --- | --- |
| `app/failures.py` | Classification des erreurs HTTP de yt-dlp, 412 anti-robot, marqueurs de connexion |
| `app/connectors.py` | Champs `search_*_url`, `item_url`, `home_kind`, `Pagination.maximum_results` ; modèles Niconico, archive.org, PeerTube, RedGifs, Mail.ru, YouTube |
| `app/pagination.py` | Capacités et `search_config` déclaratifs, plafond de fenêtre, `keep_blank_values` |
| `app/worker.py` | `ignore_no_formats_error` en listing, application d’`item_url` |
| `app/main.py` | Libellé et `feed_kind` de l’accueil, plafond de fenêtre, `keep_blank_values` |
| `app/catalog.py` | Noms revus du lot, `access_requirement` PRX, date par entrée dans `last_check` |
| `app/static/app.js` | Libellés des états d’essai (authentification, quota, restriction, DRM…) |
| `app/template_checks.json` | Essais du lot 01 redatés ; les entrées hors lot ne sont pas touchées |
| `scripts/audit_lot.py` | Nouvel outil de sondage par lot (recherche, accueil, classements, deux pages) |
| `tests/test_lot01.py` | Nouveaux tests de contrat déterministes |
| `docs/sources-lot-01.md` | Ce rapport |
| `docs/source-audit-lot-01/` | Preuves réseau datées |

## Conflits d’intégration possibles

- `app/connectors.py`, `app/pagination.py` et `app/main.py` sont modifiés dans les mêmes zones que
  tout autre lot qui toucherait aux classements ou à la pagination. Un lot parallèle sur les
  modèles YouTube ou Vimeo entrera en conflit sur `default_connector`.
- `app/catalog.py::REVIEWED` est prévu pour grossir lot après lot ; l’ajout est additif.
- `app/template_checks.json` est réécrit en entier par `scripts/audit_templates.py --live`. Ce lot
  n’a modifié que ses vingt entrées, via `scripts/audit_lot.py --update-checks`, en conservant les
  onze autres et leur date d’origine. Relancer `audit_templates.py --live` écraserait cette
  distinction.
- `engine_version()` couvre `connectors.py`, `worker.py`, `pagination.py`, `failures.py`,
  `catalog.py` et `main.py` : **toute preuve antérieure à ce lot est désormais historique**, y
  compris `docs/source-audit-current/`.

## Comment rejouer les preuves

```
python scripts/audit_lot.py                     # sonde les vingt modèles et écrit les preuves
python scripts/audit_lot.py --template BiliBili # rejoue un seul modèle après une panne temporaire
python scripts/audit_lot.py --summarize-only    # recalcule le verdict sans toucher au réseau
python scripts/audit_lot.py --update-checks     # rafraîchit les vingt entrées de template_checks.json
```

## Validation exécutée

- `python -m unittest discover -s tests` — **70 tests, tous verts** (50 avant le lot, 20 ajoutés),
  dans `.venv` du projet, Python 3.14.6.
- `git diff --check` — sans avertissement.
- Garde-fou des dialogues natifs (`tests/test_bootstrap.py`) — inclus dans la série.
- Les essais réseau sont dans `scripts/audit_lot.py`, séparés de la série déterministe : aucun test
  de `tests/` n’ouvre de connexion sortante.
