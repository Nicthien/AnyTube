# Lot 01 — vingt modèles de recherche

Lot arrêté le 6 septembre 2026 sur la branche `codex/sources-lot-01`. Le lot 02, qui couvre les
onze modèles restants, est décrit dans [`sources-lot-02.md`](sources-lot-02.md) ; les deux lots
partagent la même révision de moteur et les corrections communes sont décrites ici.

Base : checkout séparé `C:\DEV\Projects\AnyTube-lot01`, à partir du commit `5a225fb`.

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

L’étiquette n’est plus déclarative : le lot 02 l’a rendue **déduite** du modèle lui-même, parce
qu’un cas déclaré à la main était faux (Vimeo). Voir la correction 3 du rapport du lot 02.

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

### 10. La requête du lecteur pouvait casser la recherche archive.org (`app/connectors.py`)

`archive.org/advancedsearch.php` interprète la requête dans une expression Lucene :
`mediatype:movies AND ({query})`. Une parenthèse déséquilibrée, un `:` ou un `AND` en majuscules
suffisait à faire répondre une erreur au lieu d’une liste — la recherche `1920s: silent film`
échouait, tout comme `nature )`.

L’échappement Lucene par contre-oblique **ne fonctionne pas** sur ce service : essayé le
6 septembre 2026, il déclenche `[BACKEND_ERROR] Invalid or no response from Elasticsearch`. Les
opérateurs sont donc **neutralisés** : remplacés par des espaces, et les mots-clés booléens
`AND OR NOT TO` mis en minuscules — Lucene ne les traite comme opérateurs qu’en majuscules. Les
accents et les mots du lecteur sont conservés.

Le comportement est déclaratif (`query_escape`, `none` par défaut, donc sans effet sur les
configurations existantes) et n’est activé que sur archive.org. Vérifié : les six requêtes d’essai,
y compris `) OR mediatype:audio AND (`, renvoient désormais des résultats et le filtre
`mediatype:movies` tient dans tous les cas.

### 11. Un listing refusé entrée par entrée était présenté comme vide (`app/worker.py`, `app/failures.py`)

Quand un listing ne fournit que des URL sans titre, le worker ré-extrait chaque entrée. Si cette
ré-extraction échouait, l’entrée était **silencieusement abandonnée** : une source dont toutes les
entrées sont refusées répondait « aucun résultat », ce qui désigne à tort la requête.

Le worker retient maintenant la première cause classée et la lève quand aucune entrée ne survit.
Nouveau code `unsupported_media` pour le cas où le fournisseur déclare lui-même que le média n’est
pas diffusé sous une forme lisible. C’est exactement le cas de VR SQUARE, dont l’extracteur répond
« VR SQUARE app-only videos are not supported » : la recherche fonctionne, mais rien n’est lisible.

### 12. PRX : un chemin d’authentification qui n’existait pas (`app/connectors.py`)

Les quatre modèles PRX passaient par yt-dlp, qui n’accepte que des cookies importés — or l’API CMX
de PRX demande un **jeton porteur**. Aucun réglage ne permettait donc de fournir un compte.

Les quatre modèles deviennent des connecteurs JSON vers `cms.prx.org/api/v1`, la même interface que
l’extracteur installé appelle, avec le format de réponse décrit par son code (`_embedded/prx:items`).
Un jeton déposé dans le coffre existant peut désormais être rattaché à la source ; **aucun secret
n’est demandé ni écrit ici**. L’extracteur `PRXStory` / `PRXSeries` reste utilisé pour la résolution
et la lecture.

**Implémenté, non vérifié** : sans compte PRX, la réponse reste 401 et le format exact des résultats
n’a pas pu être observé. La correspondance des champs est un test déterministe construit sur le code
de l’extracteur installé, pas sur une réponse réelle.

## Résultat par modèle

Les preuves complètes sont dans `docs/source-audit-lot-01/` (un fichier JSON par modèle, plus
`summary.json`), chacune datée et portant l’environnement, la version de Python, la version de
yt-dlp, la révision du moteur de connecteurs et la révision du modèle testé.

Environnement : `local-worktree-lot01`, Windows-11-10.0.26200-SP0, Python 3.14.6, yt-dlp 2026.08.19, révision du moteur de connecteurs `46d110e31b6b6f38`, sondage du 2026-09-06T18:06:30 UTC. Proxy de sortie configuré : non.

Chaque recherche est essayée avec trois requêtes adaptées à la plateforme, sur deux pages de trois résultats. Un modèle est déclaré au meilleur état observé : une requête en échec ne le condamne pas, et une requête qui répond ne masque pas les autres — le détail par requête figure dans les preuves.

| Modèle | Interface réellement utilisée | Recherche (3 requêtes × 2 pages) | Accueil | Classements |
| --- | --- | --- | --- | --- |
| `ArchiveOrg` | API `archive.org/advancedsearch.php` (JSON officiel) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par flux | `home:trending` : résultats reçus<br>`home:views` : résultats reçus<br>`home:recent` : résultats reçus<br>`search:views` : résultats reçus<br>`search:recent` : résultats reçus<br>`search:trending` : résultats reçus |
| `BiliBili` | yt-dlp `bilisearch` | résultats reçus · 1/3 requêtes · 6 URL distinctes, 0 répétées | quota ou filtrage · servi par recherche « vidéos » | aucun classement disponible |
| `BiliBiliSearch` | yt-dlp `bilisearch` | quota ou filtrage · 0/3 requêtes · 0 URL distinctes, 0 répétées | quota ou filtrage · servi par recherche « vidéos » | aucun classement disponible |
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
| `PRXSeries` | API CMS PRX (JSON officiel) — **remplace** le chemin yt-dlp, jeton de coffre possible | authentification requise · 0/3 requêtes · 0 URL distinctes, 0 répétées | authentification requise · servi par recherche « vidéos » | aucun classement disponible |
| `PRXSeriesSearch` | API CMS PRX (JSON officiel) — **remplace** le chemin yt-dlp, jeton de coffre possible | authentification requise · 0/3 requêtes · 0 URL distinctes, 0 répétées | authentification requise · servi par recherche « vidéos » | aucun classement disponible |
| `PRXStoriesSearch` | API CMS PRX (JSON officiel) — **remplace** le chemin yt-dlp, jeton de coffre possible | authentification requise · 0/3 requêtes · 0 URL distinctes, 0 répétées | authentification requise · servi par recherche « vidéos » | aucun classement disponible |
| `PRXStory` | API CMS PRX (JSON officiel) — **remplace** le chemin yt-dlp, jeton de coffre possible | authentification requise · 0/3 requêtes · 0 URL distinctes, 0 répétées | authentification requise · servi par recherche « vidéos » | aucun classement disponible |
| `PeerTube` | API PeerTube v1 sur Framatube (JSON officiel) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par flux | `home:trending` : résultats reçus<br>`home:views` : résultats reçus<br>`home:recent` : résultats reçus<br>`search:views` : résultats reçus<br>`search:recent` : résultats reçus |
| `PeerTubePlaylist` | API PeerTube v1 sur Framatube — **modèle identique à `PeerTube`** | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par flux | `home:trending` : résultats reçus<br>`home:views` : résultats reçus<br>`home:recent` : résultats reçus<br>`search:views` : résultats reçus<br>`search:recent` : résultats reçus |
| `RedGifsSearch` | yt-dlp `RedGifsSearch` (API RedGifs v2) | résultats reçus · 3/3 requêtes · 18 URL distinctes, 0 répétées | résultats reçus · servi par recherche « vidéos » | `search:views` : résultats reçus<br>`search:recent` : résultats reçus<br>`search:trending` : résultats reçus |

Remarques par modèle :

- `ArchiveOrg` — La requête du lecteur est neutralisée avant d’entrer dans l’expression Lucene du service.
- `BiliBili` — Modèle identique à `BiliBiliSearch` ; les écarts entre les deux ne viennent que du filtrage anti-robot de Bilibili (412), rapporté comme quota. Ce n’est pas un verdict.
- `BiliBiliSearch` — Voir `BiliBili` : même modèle, même filtrage intermittent.
- `GameJolt` — Les publications sans média sont désormais listées au lieu de faire échouer la page.
- `GameJoltSearch` — Les publications sans média sont désormais listées au lieu de faire échouer la page.
- `GoogleSearch` — Extracteur amont cassé : le repère HTML recherché n’existe plus. Aucune API sans clé pour le remplacer.
- `MailRuMusicSearch` — URL par piste reconstruite ; sans cela toutes les cartes partageaient l’URL de la recherche.
- `PRXSeries` — API PRX en 401 ; le jeton se dépose dans le coffre, aucun compte n’était disponible pour l’essai.
- `PRXSeriesSearch` — API PRX en 401 ; le jeton se dépose dans le coffre, aucun compte n’était disponible pour l’essai.
- `PRXStoriesSearch` — API PRX en 401 ; le jeton se dépose dans le coffre, aucun compte n’était disponible pour l’essai.
- `PRXStory` — API PRX en 401 ; le jeton se dépose dans le coffre, aucun compte n’était disponible pour l’essai.
- `PeerTubePlaylist` — Recherche de listes de lecture non implémentée ; le modèle sert la recherche vidéo.

Révisions de modèle effectivement testées :

- `ArchiveOrg` : `271d2ca6fbc34c53a3c9f1860561709e…`
- `BiliBili` : `8ba3ca5b9f62f56c8bdccf0c329839d5…`
- `BiliBiliSearch` : `8ba3ca5b9f62f56c8bdccf0c329839d5…`
- `Dailymotion` : `1c2ba3ac7ad66ba9b8f8897b3fd324f9…`
- `DailymotionSearch` : `1c2ba3ac7ad66ba9b8f8897b3fd324f9…`
- `GameJolt` : `8dc63e9c7fbe414b873ba749df3f44ac…`
- `GameJoltSearch` : `8dc63e9c7fbe414b873ba749df3f44ac…`
- `GoogleSearch` : `d93367657c5ed2f8bc378f5b16c9c2c8…`
- `MailRuMusicSearch` : `bd02a9a769fceaa200619e0fc69f8e32…`
- `Niconico` : `9262024d96bd4f683de05dbdaef6c590…`
- `NicovideoSearch` : `9262024d96bd4f683de05dbdaef6c590…`
- `NicovideoSearchDate` : `efa16d0530d6b23ecea5ea4d69cb9451…`
- `NicovideoSearchURL` : `9262024d96bd4f683de05dbdaef6c590…`
- `PRXSeries` : `518041b4e6cfcf2cbdee0f6bc23ff6c9…`
- `PRXSeriesSearch` : `518041b4e6cfcf2cbdee0f6bc23ff6c9…`
- `PRXStoriesSearch` : `4b66ac9895b951585caf542d86f53d72…`
- `PRXStory` : `4b66ac9895b951585caf542d86f53d72…`
- `PeerTube` : `a6497d94cc352282a20627b8d92fd585…`
- `PeerTubePlaylist` : `a6497d94cc352282a20627b8d92fd585…`
- `RedGifsSearch` : `2925c6058fb0dd483fe90f3fe2242da6…`

### Vérification de bout en bout par l'API HTTP

Les sondages ci-dessus appellent le worker directement. Un essai supplémentaire a parcouru la
**couche HTTP complète** — session, `/api/sources`, `/api/search` avec curseur, `/api/home` — le
6 septembre 2026, sur les deux modèles à pagination native les plus représentatifs :

| Modèle | Page 1 | Page 2 | Résultats communs | Curseur émis | Classement « Plus vues » | Accueil |
| --- | --- | --- | --- | --- | --- | --- |
| `Niconico` | 3 | 3 | 0 | oui | 3 résultats, **identiques au tri par défaut** | 10 vidéos, « Flux d’accueil », `feed_kind=feed` |
| `ArchiveOrg` | 3 | 3 | 0 | oui | 3 résultats, **ordre différent du tri par défaut** | 10 vidéos, « Flux d’accueil », `feed_kind=feed` |

Le classement « Plus vues » de Niconico renvoie les mêmes résultats que la recherche par défaut,
et c’est attendu : l’API Snapshot n’a pas de tri par pertinence, donc le tri par défaut des modèles
`Niconico`, `NicovideoSearch` et `NicovideoSearchURL` **est déjà** `-viewCounter`. Seul
`NicovideoSearchDate`, qui trie par date, voit ce classement changer l’ordre. Le classement n’est
pas factice, il est redondant pour trois modèles sur quatre.

## Références

Interfaces réellement appelées par les modèles de ce lot, et code des extracteurs installés
(yt-dlp 2026.08.19). Les URL de documentation ont été ouvertes le 6 septembre 2026.

| Plateforme | Interface appelée | Documentation | Extracteur installé |
| --- | --- | --- | --- |
| archive.org | `archive.org/advancedsearch.php` | [advancedsearch](https://archive.org/advancedsearch.php) | [`archiveorg.py`](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/archiveorg.py) |
| Bilibili | `api.bilibili.com/x/web-interface/search/type` (via yt-dlp) | — | [`bilibili.py`](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/bilibili.py) |
| Dailymotion | `api.dailymotion.com/videos` | [API Dailymotion](https://developers.dailymotion.com/reference/introduction) | [`dailymotion.py`](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/dailymotion.py) |
| Game Jolt | `gamejolt.com/site-api/web/search` (via yt-dlp) | — | [`gamejolt.py`](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/gamejolt.py) |
| Google Vidéos | `google.com/search?tbm=vid` (extraction HTML, via yt-dlp) | — | [`googlesearch.py`](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/googlesearch.py) |
| Mail.ru Musique | `my.mail.ru/cgi-bin/my/ajax` (via yt-dlp) | — | [`mailru.py`](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/mailru.py) |
| Niconico | `snapshot.search.nicovideo.jp/api/v2/snapshot/video/contents/search` | [Snapshot Search API v2](https://site.nicovideo.jp/search-api-docs/snapshot) | [`niconico.py`](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/niconico.py) |
| PeerTube (Framatube) | `framatube.org/api/v1/search/videos` et `/api/v1/videos` | [API REST PeerTube](https://docs.joinpeertube.org/api-rest-reference.html) | [`peertube.py`](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/peertube.py) |
| PRX | `cms.prx.org/api/v1/stories/search` et `/series/search` | [racine de l’API](https://cms.prx.org/api/v1) | [`prx.py`](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/prx.py) |
| RedGifs | `api.redgifs.com` via `redgifs.com/browse` (via yt-dlp) | — | [`redgifs.py`](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/redgifs.py) |

Un tiret signifie qu’aucune documentation publique n’a été trouvée : l’interface n’est connue que
par le code de l’extracteur installé, ce qui est en soi une fragilité.

## Ce qui reste à faire

1. **PRX (4 modèles)** — `cms.prx.org/api/v1` répond 401 sur `stories/search`, `series/search` et
   sur une histoire isolée ; la racine `/api/v1` reste publique. Le chemin d’accès par jeton de
   coffre est maintenant en place (correction 12), mais **il n’a pas pu être essayé** faute de
   compte PRX : le format des résultats reste à confirmer sur une réponse réelle.
2. **GoogleSearch** — `gvsearch` extrait `class="dXiKIc"` de `google.com/search` ; ce marqueur
   n’existe plus, l’extracteur renvoie zéro entrée sans erreur. Aucune API vidéo Google publique
   sans clé n’est disponible ; l’API Programmable Search demande une clé, donc un accès de coffre
   du même type que Vimeo. **Résultat vide constaté, cause identifiée en amont, correction non
   faite.**
3. **BiliBili / BiliBiliSearch** — les deux modèles sont **identiques octet pour octet** ; leurs
   écarts de résultat viennent uniquement du filtrage anti-robot de Bilibili (412 après la première
   requête). Ce n’est ni une panne définitive ni une réussite complète.
   Deux atténuations ont été **mesurées et écartées** le 6 septembre 2026 : espacer les requêtes
   (0 s → 1/3 réussites, 3 s → 0/3, 6 s → 2/3) ne montre aucune amélioration monotone, et remplacer
   le cookie `buvid3` synthétique de yt-dlp par un cookie délivré par
   `api.bilibili.com/x/frontend/finger/spi` ne donne que 2/4 contre 1/4. Aucune atténuation côté
   client n’est donc justifiée ; le refus est intermittent et la correction relève de l’extracteur
   amont.
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
7. **archive.org** — corrigé (correction 10). Reste ouvert : la neutralisation retire les
   opérateurs au lieu de les échapper, donc une recherche volontairement syntaxique
   (`"titre exact"`) n’est pas possible sur cette source.
8. **Niconico** — pas de tri par pertinence dans l’API ; pas de nom de chaîne ; classement officiel
   `nvapi.nicovideo.jp` non exploité car il exige un en-tête `X-Frontend-Id` que le modèle
   déclaratif ne peut pas porter.
9. **Pagination par préfixe** — pour toute source sans pagination native, la page suivante relance
   la recherche complète. Mesuré sur Bilibili : 1 à 2 résultats sur 3 se répètent en page 2. Les
   neuf modèles JSON du lot qui ont répondu — archive.org, Dailymotion (2), Niconico (4) et
   PeerTube (2) — utilisent une pagination native et n’ont montré **aucune** répétition.
10. **Accueil des sources sans flux** — `home_query` vaut « vidéos » pour toutes les sources sans
   flux publié. Sur Game Jolt, Mail.ru et RedGifs, cela revient à chercher un mot français ; les
   trois ont malgré tout renvoyé des résultats, mais la pertinence n’est pas évaluée. Le champ est
   modifiable par le lecteur dans Mes sources ; aucun choix éditorial n’a été imposé.
11. **Filtres de durée et de date** — ils restent réservés à Dailymotion. Les classements ont pu
   être rendus déclaratifs parce qu’un classement est une URL entière ; un filtre ne l’est pas :
   deux URL complètes ne se composent pas (durée **et** date **et** classement). Niconico
   (`filters[lengthSeconds][gte]`) et archive.org (plages de dates) exposent pourtant ces filtres.
   Les rendre déclaratifs demande de décrire des **paramètres** — nom, valeur, et un emplacement
   pour un horodatage calculé — au lieu d’URL complètes. Conception identifiée, non implémentée.
12. **Toutes plateformes** — lecture, audio, direct, sous-titres et téléchargement restent **non
   vérifiés** pour ce lot. Aucune recette navigateur, aucune recette Docker et aucune recette
   Unraid n’a été exécutée sur cette branche.

## Fichiers modifiés

| Fichier | Nature |
| --- | --- |
| `app/failures.py` | Classification des erreurs HTTP de yt-dlp, 412 anti-robot, marqueurs de connexion, code `unsupported_media` |
| `app/connectors.py` | Champs `search_*_url`, `item_url`, `home_kind`, `query_escape`, `Pagination.maximum_results` ; modèles Niconico, archive.org, PeerTube, RedGifs, Mail.ru, PRX, YouTube |
| `app/pagination.py` | Capacités et `search_config` déclaratifs, plafond de fenêtre, `keep_blank_values` |
| `app/worker.py` | `ignore_no_formats_error` en listing, application d’`item_url`, cause conservée quand toutes les entrées sont refusées |
| `app/main.py` | Libellé et `feed_kind` de l’accueil, plafond de fenêtre, `keep_blank_values` |
| `app/catalog.py` | Noms revus du lot, `access_requirement`, table `LIMITATIONS`, date par entrée dans `last_check` |
| `app/inventory.py` | Décompte séparé des modèles de recherche examinés par lot, sans promouvoir la plateforme |
| `app/static/app.js` | Libellés des états d’essai et affichage des limitations connues et des accès requis |
| `app/template_checks.json` | Essais du lot 01 redatés ; les entrées hors lot ne sont pas touchées |
| `scripts/audit_lot.py` | Nouvel outil de sondage par lot (recherche, accueil, classements, deux pages) |
| `tests/test_lot01.py`, `tests/test_lot02.py` | Nouveaux tests de contrat déterministes |
| `tests/test_sources_expansion.py` | Garde-fou : un modèle examiné ne promeut pas sa plateforme |
| `README.md`, `README.en.md` | État réel des 31 modèles et limites, dans les deux langues |
| `docs/sources-lot-01.md`, `docs/sources-lot-02.md` | Les deux rapports |
| `docs/source-audit-lot-01/`, `docs/source-audit-lot-02/` | Preuves réseau datées |

## Conflits d’intégration possibles

- `app/connectors.py`, `app/pagination.py` et `app/main.py` sont modifiés dans les mêmes zones que
  tout autre lot qui toucherait aux classements ou à la pagination. Un lot parallèle sur les
  modèles YouTube ou Vimeo entrera en conflit sur `default_connector`.
- `app/catalog.py::REVIEWED` est prévu pour grossir lot après lot ; l’ajout est additif.
- `app/template_checks.json` est réécrit en entier par `scripts/audit_templates.py --live`. Ce lot
  n’a modifié que ses vingt entrées, via `scripts/audit_lot.py --update-checks`, en conservant les
  onze autres et leur date d’origine. Relancer `audit_templates.py --live` écraserait cette
  distinction.
- `engine_version()` couvre entre autres `connectors.py`, `worker.py`, `pagination.py`,
  `failures.py`, `catalog.py` et `main.py` : **toute preuve antérieure à ces lots est désormais
  historique**, y compris `docs/source-audit-current/`. Une simple retouche de commentaire dans un
  de ces fichiers change la révision et périme les preuves ; c’est voulu, mais cela impose de
  figer le code avant de lancer une campagne d’essais.
- `app/inventory.py` n’est pas couvert par `engine_version()` : son décompte peut évoluer sans
  périmer les preuves.

## Comment rejouer les preuves

```
python scripts/audit_lot.py --batch lot-01       # sonde les vingt modèles et écrit les preuves
python scripts/audit_lot.py --batch all          # sonde les 31 modèles des deux lots
python scripts/audit_lot.py --template BiliBili  # rejoue un seul modèle après un refus temporaire
python scripts/audit_lot.py --summarize-only     # recalcule le verdict sans toucher au réseau
python scripts/audit_lot.py --update-checks      # rafraîchit les entrées du lot dans template_checks.json
```

`--template` n’écrit le résumé que pour les modèles rejoués : enchaîner `--summarize-only` pour
reconstruire le résumé complet du lot à partir des preuves déjà stockées.

## Validation exécutée

- `python -m unittest discover -s tests` — **84 tests, tous verts** (50 avant les lots, 34 ajoutés
  par les lots 01 et 02), dans `.venv` du projet, Python 3.14.6.
- `git diff --check` — sans avertissement.
- Garde-fou des dialogues natifs (`tests/test_bootstrap.py`) — inclus dans la série.
- Les essais réseau sont dans `scripts/audit_lot.py`, séparés de la série déterministe : aucun test
  de `tests/` n’ouvre de connexion sortante.
