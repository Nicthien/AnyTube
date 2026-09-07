# Sources : accélération et exploration en cours

## État actuel vérifié

42 modèles de recherche, moteur `b3239e93083da870`, 146 tests passent.
Onze ajouts depuis la passation : NRK, Wikimedia, Apple Podcasts, Microsoft Learn,
OpenRec, ARTE, ARD, CBS News, Patreon, ToonGoggles et TU Graz. Les changements restent locaux,
sans publication ni déploiement.

Campagne actuelle : 42 modèles, 31 avec résultats, 1 limité, 1 vide,
5 demandant une authentification, 3 indisponibles et 1 non pris en charge.
Durée : 290,033 s avec concurrence 4, 215 scénarios exécutés et 5 réutilisés
(`source-audit-current/summary-campaign-42.json`). BiliBili répond à une seule
requête ; ses autres requêtes et son accueil restent limités.
Reprise sans changement : 0.985 s, aucun scénario réseau exécuté,
220 réutilisés (`resume-performance-42.json`). Les 42 révisions effectives et
statuts publiés concordent avec le moteur actuel. Ces durées ne constituent pas
une comparaison contrôlée avec les anciennes campagnes.

ToonGoggles : modèle de recherche d'émissions ajouté, audit ciblé positif pour
robot, bernard, adventure et l'accueil (`source-audit-toongoggles/`). Les nouvelles
URL d'émissions et d'épisodes sont prises en charge. L'image Docker
`sha256:3e20be538fd37c2d722480b83cf6d6195c982086ed62d4740370cdf0dca2d836`
renvoie trois résultats, trois épisodes avec titres et cinq formats pour Table Tennis
(`docker-toongoggles-probe.json`). Lecture navigateur confirmée ensuite sur
l'image `e7e758f50bc929986b8daa0a58de8c850b82fef5117a96902313d62baa1edb33`,
moteur `daf113d8ef41153b` : Table Tennis progresse de 14,236 à 22,743 s,
lecture active, qualité adaptative 360p puis 720p, image contrôlée visuellement.
Preuve : `docker-toongoggles-browser-playback.json`. Les longs délais du navigateur
avant lecture persistent ; aucune cause n'est établie. Lecture arrêtée et onglet IAB
fermé. Nettoyage du conteneur non confirmé : API Docker indisponible lors du contrôle.

Patreon : recherche de créateurs, pagination native et collections avec titres,
identifiants et dates. Les publications sans média ou à accès restreint proposent
un lien externe, sans actions de lecture/conservation ; vérifié dans le navigateur
local. Un média public Smarter Every Day est lu depuis sa collection : progression
de 6,46 à 21,25 s, qualité adaptative 240p puis 144p
(`patreon-browser-playback.json`). Deux pages de collection sont distinctes
(`patreon-pagination-probe.json`). L'audit ciblé de recherche précédent était
positif pour science, piano, history et l'accueil (`source-audit-patreon/`).

Image utilisée pour les contrôles Patreon ci-dessous :
`sha256:9c82822f3271034a9bfa13d408e129b752b46c786d6439c20c87c6613c7299f0`.
Son moteur est `5ab317d48c4eff9d`. Les indicateurs Patreon « sans média » et
« accès requis » sont confirmés dans son worker (`docker-patreon-flags.json`).
La précédente image avait aussi réussi recherche, collection et extraction de
53 formats pour le média public (`docker-patreon-probe.json`). Cela ne prouve
pas une lecture navigateur via Docker.

Lecture navigateur via Docker confirmée ensuite sur le même média public :
progression de 14,03 à 25,66 s, lecture active en 240p, image du conteneur Patreon testé
(`docker-patreon-browser-playback.json`). Les délais initiaux de connexion et
de collection restent inexpliqués ; la réussite suivante ne les efface pas.
Le conteneur temporaire `anytube-patreon-browser-check` et son onglet ont été
arrêtés après le contrôle ; ses données en mémoire ne sont pas conservées.

Lecture navigateur déjà observée sur un média Microsoft Learn, ARTE, ARD, CBS
et Patreon, à des révisions différentes conservées dans leurs preuves.
Aucun de ces essais ne certifie une plateforme entière. Le refus régional NRK
est identifié comme `geo_restricted` ; les refus CBS intermittents restent
consignés. Les candidats nécessitant un accès ou une nouvelle investigation
sont dans `source-candidate-status.json`.

Performance : la campagne précédente de 39 modèles a pris 306,529 s ; sa reprise
0,924 s dans l'audit (environ 2,2 s pour la commande), avec 208 scénarios réutilisés
et aucun exécuté (`source-audit-current/resume-performance.json`). Ce gain mesure
le travail évité, pas un réseau plus rapide. La campagne historique des 40 modèles (284,142 s) est conservée dans
`source-audit-current/summary-network.json`.

Suite : poursuivre la validation navigateur de TU Graz et les candidats non bloqués ;
contrôler le nettoyage du conteneur ToonGoggles lorsque Docker sera accessible.
TU Graz est ajouté via son API publique `/search/episode.json` : recherche science,
data, mathematik et accueil positifs, pagination native par offset, durées converties
depuis les millisecondes. Consolidation des 42 modèles sans réseau : toutes les
révisions correspondent au moteur actuel. La lecture TU Graz reste non vérifiée.

Le triage compte 27 familles avec modèle ; ses autres entrées sont des pistes,
pas des sources dont la compatibilité est établie.

Validation navigateur ToonGoggles : la recherche Bernard aboutit, mais le parcours
vers ses épisodes a révélé un refus « Ajoutez et activez une source » : la sélection
ne reconnaissait que les anciennes URL yt-dlp. `select_source` accepte désormais
les URL des adaptateurs modernes uniquement avec une source ToonGoggles activée,
et respecte le source_id demandé. Test de régression : émission, épisode, source
désactivée, autre identifiant et faux domaine. Les 144 tests passent et
`git diff --check` ne signale aucune erreur. Image reconstruite avec succès au moteur
`daf113d8ef41153b` ; nouvelle lecture navigateur encore à vérifier. La campagne
41 modèles a été interrompue volontairement après cette découverte ; ses résultats
partiels ne constituent pas une campagne complète de la nouvelle révision.

Contrôle des routes Docker après correction (`docker-toongoggles-api-check.json`) :
collection Bernard HTTP 200 en 1,479 s, titres Table Tennis/Aerobics/Swimming ;
résolution du premier épisode HTTP 200 en 2,163 s avec cinq formats. Ces appels
passent par la sélection de source corrigée. La lecture navigateur reste non prouvée :
deux connexions IAB ont expiré, contre 0,060 s pour la connexion API directe ;
Chrome a signalé une interface d'extension bloquant l'automatisation. Aucune cause
applicative n'est déduite de ces difficultés de navigateur.

Mesures HTTP directes du conteneur corrigé (`docker-toongoggles-timings.json`) :
recherche Bernard 1,731 s (un résultat), accueil 1,444 s (neuf résultats),
puis même accueil en cache 0,006 s (neuf résultats). Mesures locales bornées,
qui ne prouvent ni la vitesse de production ni celle de toutes les sources.

TU Graz : l'extracteur installé attendait une ancienne enveloppe JSON et échouait
sur une vidéo publique. Adaptateur ajouté pour les enveloppes actuelle et historique,
avec sélection stricte de l'identifiant demandé, conversion des millisecondes et
utilisation des pistes effectivement publiées. Résolution Windows : une piste en
1,513 s, titre et durée corrects (`tubetugraz-resolve-current.json`). Les tests
vérifient aussi l'absence de requêtes vers des manifestes devinés et le refus de
substituer une autre vidéo. Lecture navigateur encore à vérifier. Extraction Docker et décodage FFmpeg des
deux premières secondes réussis (une piste, aucune erreur), en 3,633 s au total :
`docker-tubetugraz-decode.json`. Image `647b6dc46aa1f64567ef90a602ab15ac9313d0c7f98a724e83b8351027d2b198`.
Les 42 preuves de recherche ont été renouvelées après cette adaptation (bilan actuel ci-dessus).

Contrôle média Docker complémentaire au moteur `b3239e93083da870` : Wikimedia
(six formats, piste vidéo) et Apple Podcasts (un format, piste audio) extraient et
décodent deux secondes sans erreur FFmpeg. Durées totales respectives : 2,209 s et
3,689 s. Preuve `docker-additional-decode.json`. Ces essais ne prouvent pas la
lecture via le relais et le lecteur navigateur de l'application.

Ordonnancement de l'audit : les durées historiques servent désormais à lancer
les fournisseurs lents en premier même après changement du moteur. Elles ne servent
jamais à valider ni à réutiliser une preuve : la reprise conserve ses signatures
strictes de révision et d'environnement. Les 146 tests passent, y compris la reprise
qui invalide les anciens scénarios. Le gain de temps mural de ce changement reste
à mesurer ; il n'affecte pas l'audit déjà lancé, dont l'ordre était fixé au départ.

## Historique des validations

L'audit publie désormais des compteurs explicites : mode réseau, reprise ou
consolidation seule, scénarios exécutés/réutilisés et preuves regroupées.
La dernière reprise des 40 modèles a réutilisé 212 scénarios sans appel de scénario
réseau, en 1,135 s dans l'audit. La publication des statuts utilise le bilan
recalculé et conserve la date d'observation, même si le fichier individuel contient
un ancien statut agrégé. Ces changements d'outillage ne modifient pas le moteur.

Les sections suivantes décrivent les révisions citées à leur date et peuvent
être dépassées par l'état actuel ci-dessus.

Validation Docker locale : image `anytube:sources-check` construite avec succès,
id `sha256:36c312e04b1bf65d54517c76ec0ddc6df31b8aa2454a6ac0cc23a74145045694`.
Les huit modèles déclaratifs et les adaptateurs ARTE/Microsoft s'importent sous
Linux, moteur identique `694f559bfd8be29e`. Un conteneur temporaire sans réseau
extérieur, sans port publié et avec données en tmpfs répond HTTP 200 sur /api/health ;
FFmpeg, FFprobe et Node sont détectés. Conteneur arrêté et supprimé après contrôle.
Cela valide la construction et le démarrage, pas une lecture réseau sous Docker
ni un déploiement sur le serveur utilisateur.

Sondages réseau dans cette image : CBS News renvoie trois résultats de recherche,
mais sa page Nature: Newfoundland répond HTTP 406 à yt-dlp sous Docker alors
qu'un essai Windows contemporain réussit. ARTE Le Québec boréal résout onze formats
dans Docker. Observations dans `docker-source-probe.json`. Les preuves Windows
ne doivent donc pas être assimilées à une compatibilité de lecture Docker ; le
refus CBS reste à diagnostiquer dans cet environnement.

Contre-vérification : sans modifier l'image ni le code, la page CBS répond ensuite
HTTP 200 sous Windows et Docker. yt-dlp puis le worker protégé AnyTube extraient
six formats sous Docker. Le refus 406 initial n'est donc plus reproductible ;
il reste une observation intermittente, pas une incompatibilité Linux démontrée.
La lecture dans un navigateur via le serveur Docker reste à vérifier.

Autres extractions avec le worker Docker : Wikimedia renvoie six formats pour
Nature montage around Aberfeldy ; Apple Podcasts renvoie un format pour l'épisode
science testé. Le programme NRK KOID30001224 est refusé avec le message explicite
« Ikke tilgjengelig utenfor Norge » (indisponible hors de Norvège). La recherche
NRK ne prouve donc pas la lecture depuis ce poste. Ces trois sondages, limités à
un média chacun, sont conservés dans `docker-additional-source-probe.json`.

## Audit incrémental (6 septembre 2026)

`scripts/audit_lot.py` dispose maintenant de :

- `--resume` : reprend les scénarios terminés, avec leur date d'observation conservée.
  La clé inclut configuration, révision, environnement, requête, classement, taille de page
  et délai. Omettre cette option pour refaire les mesures, y compris les anciens échecs.
- `--concurrency 1..4` : nombre de modèles traités simultanément (2 par défaut).
  Le moteur conserve sa limite globale de quatre processus et deux par fournisseur.
  Les variantes yt-dlp partagent la famille ; les connecteurs JSON partagent l'hôte API.
- `--timeout N` : délai maximal d'un appel au worker, hors attente du sémaphore global.
- Durées par page et campagne ; sauvegarde atomique après chaque scénario.
- `summary-selection.json` pour un essai ciblé, sans écraser `summary.json` du lot entier.
- Refus des identifiants inconnus et de la publication d'une preuve d'instance comme
  preuve du modèle par défaut.

Les checkpoints locaux `.checkpoints/` sont ignorés par Git. Ils ne constituent pas une
nouvelle recette réseau lorsqu'ils sont réutilisés. Les pages d'un scénario interrompu
sont rejouées ; les autres scénarios restent acquis.

Exemple :

```powershell
./.venv/Scripts/python.exe scripts/audit_lot.py --batch all --concurrency 4 --resume
```

Essai réel sur ArchiveOrg, dix scénarios, le 6 septembre : **42,550 s** pour le passage
réseau puis **0,707 s** pour la reprise. Ces durées internes excluent le démarrage du
script. Cela mesure le travail évité, pas une accélération du réseau. Trois recherches,
accueil et six classements ont reçu des résultats. Lecture non testée.
Preuves de travail : `.local/audit-resume-validation/`.

La révision globale des preuves reste conservatrice. Sa séparation par capacité et
connecteur reste à implémenter avec une analyse des dépendances ; ne pas retirer des
fichiers du hash simplement pour conserver artificiellement les preuves.

## Premier examen des candidats

Observations depuis ce poste, sans identifiants et sans contournement :

| Famille | Observation | Suite |
| --- | --- | --- |
| Rutube | `GET https://rutube.ru/api/search/video/?query=nature&page=1&limit=3` : HTTP 403 | Refus ponctuel, ne prouve pas une impossibilité ; rechercher une interface utilisable et retester ultérieurement |
| RTVE | `/api/videos.json?size=3` répond, mais `text=naturaleza` et `title=...` ne filtrent pas ; nature, musique et chaîne inexistante donnent les mêmes trois identifiants | Trouver l'interface réellement utilisée par la recherche RTVE Play ; ne pas publier ce flux comme une recherche |
| NHK | API `showsapi` accessible ; SDK officiel identifie une recherche POST distincte `nwapi/showssearch/v1/{index}/list.json` | Le premier POST renvoie 400 ; analyser le contrat SDK, le besoin de clé et le corps imbriqué avant implémentation |
| ORF | Le site utilise `search-partial/episodes/{query}` ; appel anonyme à l'API v4.3 : HTTP 401 | Examiner les possibilités d'accès documentées ; pas de connecteur validé |
| Radio France | Open API GraphQL protégée par clé attribuée après demande | Compte et contrat des recherches à examiner ; aucune requête authentifiée effectuée |

Références primaires :

- [Radio France : introduction et accès](https://developers.radiofrance.fr/doc/)
- [NHK : SDK](https://www3.nhk.or.jp/nhkworld/assets/javascripts/api-sdk.js)
- [NHK : description des ressources](https://www3.nhk.or.jp/nhkworld/assets/api_sdk/api3.json)
- [ORF ON](https://on.orf.at/) : scripts publics consultés, version frontend 2.11.2.

Ces cinq familles ne sont pas déclarées intégrées. Continuer leur examen, puis les autres
candidats du triage. Les 233 mentions d'API et de recherche sont un indice lexical,
jamais un nombre garanti de connecteurs réalisables. Aucun push ni déploiement effectué.

## Premier modèle ajouté : NRK TV

Le modèle `NRKTV` est maintenant proposé dans le catalogue. Recherche via l'API publique
documentée [NRK Search](https://psapi.nrk.no/documentation/openapi/search/openapi.json),
sur les programmes et séries TV, sans compte. Les URL relatives de résultats sont
reconstruites sur `tv.nrk.no`, pas sur l'hôte API. La base d'URL déclarative est validée,
et chaque URL résultante passe toujours les contrôles d'adresse publique.

Recette réseau du 6 septembre, `docs/source-audit-lot-03/NRKTV.json` : trois requêtes
norvégiennes (`natur`, `musikk`, `nyheter`), deux pages de trois résultats par requête ;
la seconde page contient trois nouvelles URL dans chacun des trois cas. L'accueil est
explicitement une recherche `natur`, pas un flux éditorial. Aucun classement ou filtre
supplémentaire n'est annoncé.

Le paramètre `page` documenté est ignoré sur l'interface observée : premier essai répété
à l'identique. La pagination livrée augmente donc `maxResultsPerPage` puis découpe le
préfixe côté AnyTube, avec la limite existante de 100 résultats.

Une série a été parcourue via le worker réel : `natur-i-endring`, trois épisodes et
une suite disponible (`NRKTV-collection.json`). Les locateurs yt-dlp `nrk:IDENTIFIANT`
sont convertis en liens publics de programmes. L'extracteur plat ne fournit pas les
titres et vignettes de ces épisodes : ils restent sans ces métadonnées pour l'instant.
La lecture vidéo, les droits géographiques, l'audio, les sous-titres, le direct et le
téléchargement restent non vérifiés. Aucun statut global « plateforme vérifiée ».

Validation locale : 106 tests déterministes passent, `git diff --check` passe.
La modification du moteur rend historiques les preuves des lots antérieurs ; campagne
globale à rejouer après les prochaines modifications communes.

## Wikimedia Commons et Apple Podcasts

Deux modèles supplémentaires rejoignent le lot 03 (trois au total, avec NRK TV).

- **Wikimedia Commons** : recherche limitée aux fichiers vidéo, pagination par décalage
  `gsroffset`, vignettes et durées. Les recherches `nature`, `piano` et `science` renvoient
  chacune trois nouvelles URL sur la seconde page. Une réponse vide ne contient pas de
  liste : elle est acceptée seulement lorsque le total explicite est zéro. Un payload
  d'erreur ou un total absent reste une erreur. Le client s'identifie par User-Agent.
- **Apple Podcasts** : recherche d'épisodes dans le catalogue FR via iTunes, liens vers
  les épisodes, nom d'émission, image, date et durée convertie de millisecondes en
  secondes. `science` et `histoire` répondent ; `musique` est vide dans cette recette.
  Pagination par préfixe limitée : l'API renvoie parfois moins de résultats que demandé.
  Aucun abonnement ou compte externe n'a été utilisé.

Résolution via les workers réels : un fichier vidéo Wikimedia expose six formats HTTPS ;
un épisode Apple Podcasts expose un format HTTPS. Preuves expurgées des URL média dans
`Wikimedia-resolve.json` et `ApplePodcasts-resolve.json`. Cela ne vérifie pas encore le
décodage navigateur, le téléchargement, les sous-titres ou le direct.

Références : [recherche MediaWiki](https://www.mediawiki.org/wiki/API:Search),
[métadonnées des fichiers](https://www.mediawiki.org/wiki/API:Imageinfo),
[iTunes Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html).
L'entité `podcastEpisode` est observée dans les réponses réelles ; elle n'apparaît pas dans
la liste des entités de cette documentation archivée Apple. Le comportement observé est
donc consigné sans lui attribuer une garantie documentaire.

Audius a également été sondé : `api.audius.co/v1/tracks/search` répond HTTP 403 depuis
ce poste ; aucun modèle n'a été ajouté à partir de cet essai.

Les trois modèles du lot 03 ont été réaudités sur la révision `8c7c7cee02c9866c`.
109 tests déterministes passent ; `git diff --check` passe. Le catalogue contient
désormais 34 modèles de recherche, sans certification globale de plateforme.

## Génération de candidats

`scripts/scaffold_connector.py` prépare un connecteur JSON depuis une réponse publique
enregistrée localement. Il détecte une liste non vide, cherche les chemins des champs
connus sur ses dix premières entrées et valide le résultat avec `Connector`. Plusieurs
listes plausibles nécessitent `--results-path`. Aucun contenu de la réponse n'est copié
dans le connecteur : seuls les chemins sont retenus. Les paramètres usuels de clé ou
jeton dans l'URL sont refusés ; ne fournir que des endpoints publics sans secret.

```powershell
./.venv/Scripts/python.exe scripts/scaffold_connector.py --sample .local/scaffold-nrk-sample.json --extractor NRKTV --search-url 'https://psapi.nrk.no/search?q={query}&medium=tv&maxResultsPerPage={limit}' --base-url https://tv.nrk.no/ --output .local/scaffold-nrk.json --probe natur
```

`--probe` est facultatif et effectue deux pages via le worker protégé habituel, avec
preuves dans un fichier `.probe.json`. Sans cette option, aucune requête réseau.
Le candidat n'est jamais ajouté automatiquement au catalogue. Examiner pertinence,
type des URL (média ou collection), pagination, dates, unités, variantes et lecture.
L'outil couvre les API JSON GET ; les corps POST et les transformations spécifiques
restent à écrire. La pagination native n'est pas devinée depuis une seule réponse.

Exemple NRK exécuté réellement : candidat généré, recherche avec résultats sur deux
pages. 113 tests déterministes passent, `git diff --check` passe. Ces fichiers de
scripts ne changent pas la révision du moteur.

## Modèles séparés du moteur

Les trois nouveaux modèles sont maintenant des données dans `app/search_templates.json`.
Le catalogue lit leur nom et leur limitation ; `default_connector()` valide leur
configuration avec le même modèle Pydantic que les connecteurs personnalisés.
Ajouter une entrée pour un extracteur installé ne demande plus de modifier le moteur.
La configuration effective reste incluse dans `revision(config)` : une modification
fonctionnelle périme la preuve de la source concernée, mais pas celle des autres.
Un changement de libellé ne périme pas les preuves d'exécution. Un changement du moteur
commun continue de les périmer toutes, par prudence.

Les modèles historiques restent dans leurs définitions existantes ; les nouvelles
entrées doivent utiliser le fichier JSON lorsque le moteur déclaratif suffit. Ajouter
aussi l'identifiant au lot d'audit choisi et des requêtes représentatives dans le script.
Le fichier JSON est inclus par le `COPY app ./app` du Dockerfile. Les données sont
chargées au démarrage : redémarrer le service après leur livraison. Cette modification
n'a pas été déployée.

116 tests déterministes passent. Une campagne complète est lancée dans
`docs/source-audit-latest` pour les 34 modèles, concurrence 4, délai 30 s par worker.

Le triage ajoute `search_route_hint` : une route littérale ressemblant à une recherche
est distinguée des helpers yt-dlp `_search_regex` et assimilés. Le rapport
`family-triage-next.json` classe 60 candidats. Sur 908 familles restantes : 404 ont une
API repérée, 231 une API et une mention générique de recherche, 14 une API et un indice
de route de recherche. Aucun de ces nombres n'est une estimation de compatibilité.

Gronkh : les deux sondages publics de `api.gronkh.tv/v1/search` échouent à la validation
TLS (certificat auto-signé signalé par Python). Aucun contournement du certificat ni
connecteur livré. TED : la page des conférences fournit des données Next.js, mais
son interface de recherche JSON stable n'est pas encore identifiée ; pas de modèle
figé sur un identifiant temporaire de build.

## Campagne complète et Microsoft Learn

La campagne des 34 modèles est terminée : 284,901 secondes, 22 modèles avec résultats,
2 limités par le fournisseur, 1 vide, 5 demandant une authentification, 3 en panne
temporaire et 1 média non pris en charge. `summary-network.json` conserve ce passage.
L'affichage final Windows a échoué sur des caractères non représentables en cp1252,
après sauvegarde des preuves et des checks ; la sortie console JSON utilise désormais
des échappements ASCII. La reprise a terminé en 0,944 seconde sans refaire les sondages.

**Microsoft Learn · séries et événements** a ensuite été ajouté uniquement au manifeste
de données, sans changer la révision moteur `a6eb4c62bd8afe07`. Le catalogue compte
35 modèles. Les recherches `python`, `azure`, `sql` retournent chacune trois nouvelles
collections sur la seconde page. Une requête témoin inexistante renvoie zéro résultat.
Interface repérée dans les scripts du [site officiel](https://learn.microsoft.com/en-us/shows/browse) :
`/api/contentbrowser/search/shows?locale=en-us&terms=...&$top=...`.
Le paramètre `search` essayé initialement est ignoré ; le connecteur utilise `terms`.

La série Python for Beginners a été parcourue via le worker : trois liens d'épisodes,
suite disponible. L'extracteur plat omet leurs titres, images et identifiants ; cette
limite reste visible et à améliorer. Lecture non vérifiée. Pagination de recherche par
préfixe limitée à 100 ; le moteur ne supporte pas encore le nom de paramètre natif `$skip`.
La preuve est dans `MicrosoftLearnPlaylist-collection.json`. Le résumé courant regroupe
les 35 modèles, tous à la même révision, à partir des scénarios déjà observés.

CPAC : l'endpoint de recherche utilisé par l'extracteur installé renvoie HTTP 404 lors
du sondage du 6 septembre. Aucun modèle CPAC publié à partir de ce résultat.
116 tests déterministes passent ; `git diff --check` passe.

## Parcours navigateur et métadonnées Microsoft

Vérification locale du 6 septembre sur une base de test isolée, port 18090 :
la recherche `python` retourne huit séries ; cliquer sur Python for Beginners ouvre
la collection et vingt épisodes, avec un bouton pour poursuivre. Les cartes reconnues
comme collections Microsoft Learn ou NRK proposent désormais « Parcourir les épisodes ».
Les liens de médias individuels conservent leur parcours de lecture.

Le premier essai affichait vingt « Sans titre ». L'API de collection fournit pourtant
les titres, identifiants, dates, images et durées. `app/microsoft.py` conserve ces champs
pendant l'extraction plate, sans extraire chaque épisode séparément. Après correction,
les vingt titres sont visibles dans le navigateur. Deux tests couvrent les métadonnées,
la progression de pagination et le refus de chemins externes.

Le lancement de String Concepts résout le titre et les flux, mais le lecteur finit par
« Shaka Error 1001 » ; le média reste à currentTime=0, readyState=0. La lecture Microsoft
n'est donc pas validée et le relais reste à diagnostiquer. Aucun déploiement effectué.

118 tests passent ; syntaxe JavaScript et `git diff --check` vérifiés. Les modifications
du lecteur et du worker changent la révision moteur : le résumé de campagne précédent
reste une preuve historique, pas une validation de cette nouvelle révision.

### Lecture Microsoft : cause trouvée et corrigée

Le CDN renvoie les MP4 fragmentés HLS en `application/octet-stream`. Le lecteur,
ne reconnaissant pas le type derrière l'URL opaque du relais, demandait le fichier
entier (34 843 738 octets pour la variante 1080p observée). Le worker le refusait
correctement au-delà de sa limite de 8 Mio. Le fournisseur accepte pourtant les
plages : `bytes=0-868` renvoie 206 et exactement 869 octets.

Le relais reconnaît maintenant la signature MP4 `ftyp`/`styp` dans le sondage de
contenu existant et annonce `video/mp4`. La limite de taille reste inchangée.
Vérification réelle dans le navigateur local : String Concepts avance à 17,256 s,
readyState=4, paused=false. Après sélection de 720p, il atteint 47,920 s avec une
image décodée de 1280×720 et readyState=4. Cela valide ce parcours et cet épisode,
pas l'ensemble de Microsoft Learn, ni les sous-titres ou le téléchargement.

119 tests passent, dont une régression sur la détection MIME. `git diff --check`
passe. Les preuves de recherche doivent toujours être renouvelées sur la révision
finale ; aucun déploiement effectué.

### Pagination native Microsoft Learn

Le connecteur de recherche utilise maintenant `$skip` avec `$top` constant. Le modèle
de pagination accepte un dollar initial dans le nom du paramètre ; les paramètres
restent encodés par `urlencode`. Trois sondages `azure` aux offsets 0, 3 et 6 renvoient
neuf collections distinctes, sur un total annoncé de 145. Le worker réel renvoie aussi
trois collections à l'offset 120, avec une suite disponible. La limite de 100 résultats
du mode préfixe ne s'applique donc plus à cette source ; les pages précédentes ne sont
plus retéléchargées pour obtenir la suivante. Les sources déjà enregistrées avec une
ancienne configuration ne sont pas migrées automatiquement par ce changement.

Audit frais des quatre modèles dans `source-audit-lot-03-native` : 14,729 secondes,
quatre modèles avec résultats. Le fichier `MicrosoftLearnPlaylist-offset120.json`
conserve le sondage au-delà de l'ancienne limite. 120 tests passent et
`git diff --check` passe. Les autres modèles n'ont pas été réaudités sur cette révision.

### Mise à jour des sources enregistrées

Parcours existant vérifié sur le compte de test local : Mes sources → Configurer →
Charger le modèle par défaut → comparer → Charger ces modifications dans le formulaire →
Enregistrer. Microsoft Learn passe de `prefix/page` à `offset/$skip`. En rouvrant la
comparaison après enregistrement, l'application affiche « Aucune différence ».
Cela ne modifie pas les sources de l'installation publiée.

L'éditeur expose maintenant le chemin du total, la base des liens relatifs et l'unité
des durées. Il conserve aussi les propriétés avancées de pagination (dont
`maximum_results`) lorsqu'on enregistre le formulaire ; auparavant cet objet était
reconstruit sans elles. Les nouveaux champs ont été observés dans le navigateur.
120 tests passent, syntaxe JavaScript et `git diff --check` vérifiés.

### Éviter de réexaminer les mêmes impasses

`source-candidate-status.json` consigne neuf pistes déjà examinées, avec date et motif.
Simplecast y figure : son helper `_call_search_api` envoie une URL exacte au service,
et ne constitue pas une recherche par mots-clés. Cela ne prouve pas l'absence d'une
autre interface ; aucune n'a été identifiée dans cet examen.

Le triage conserve ces pistes dans `held_candidates` et les retire du classement de
travail par défaut. `--include-held` permet de les réexaminer lorsqu'un accès ou le
service change ; ce ne sont pas des exclusions définitives. Le rapport régénéré compte
20 familles avec modèle et 907 restantes, dont 403 avec un indice d'API JSON. Ces
chiffres restent des indices de triage, pas des garanties de compatibilité.

Examen suivant : recherche Rumble `nature` via le worker réel refusée avec HTTP 403
et contrôle Cloudflare signalé par yt-dlp. TV2Hu utilise `/api/search/{video_id}` pour
charger une fiche ; Adult Swim envoie à `/api/search` une requête GraphQL par slug.
Aucune recherche textuelle identifiée dans ces deux extracteurs. Ces trois pistes
rejoignent les observations datées (12 au total). Le triage exclut aussi les fragments
d'hôte comme `www.` capturés avant une interpolation : ce ne sont pas des API fixes.

### Candidat OpenRec / Mellow Fan confirmé pour la recherche

`docs/openrec-discovery.json` conserve les résultats réduits de quatre sondages publics
de `/external/api/v5/search-movies` sur `public.mellow-fan.com`. Le paramètre
`search_query` agit : minecraft donne trois entrées, un témoin inexistant zéro, et
佐々木 quarante. La page 2 fournit d'autres identifiants. L'API ignore toutefois
`limit=3` et utilise des pages de 40 : un connecteur page standard sauterait des
résultats. Il faut adapter cette taille fixe avant publication. Les liens doivent
aussi choisir `/live/` ou `/movie/` selon `is_live`, comme l'extracteur installé.
Recherche prometteuse, mais modèle et lecture pas encore livrés.

CiscoLiveSearch installé échoue avec HTTP 400 sur l'API Rainfocus lors du sondage.
La recherche textuelle doit être reconfirmée avant tout nouveau modèle Cisco.

La pagination JSON accepte désormais `fixed_page_size` pour une API à numéros de
page. Le moteur récupère uniquement les blocs qui recouvrent la fenêtre demandée,
puis extrait les résultats à la bonne position. Tests : franchissement 38→46 dans
des blocs de 40, dernière page partielle, et résultats restants dans une petite page
finale. 122 tests passent. Le sondage réel OpenRec de huit entrées à l'offset 38 est
consigné dans `openrec-fixed-page-probe.json`. Ses liens sont provisoires : la sélection
`live`/`movie` doit encore être intégrée avant publication du modèle.

### Modèle OpenRec livré dans le catalogue local

Le manifeste ajoute maintenant OpenRec / Mellow Fan : 36 modèles de recherche.
`video_url_boolean_path` choisit entre `video_url` (vrai) et `video_url_false` (faux).
Les deux URL sont validées et l'identifiant encodé ; un booléen absent ou représenté
par une chaîne est refusé. OpenRec utilise `/is_live` pour les routes `/live/` et
`/movie/`, sans confondre ce type d'archive avec une diffusion actuellement en direct.

Audit dans `source-audit-openrec` : minecraft, 佐々木 et ゲーム renvoient des résultats,
ainsi que l'accueil. Pagination fixe de 40 conservée. Trois tentatives de résolution
des résultats minecraft : aucun format pour le premier, abonnement requis pour les
deux suivants. Ces limites sont conservées dans `resolve.json` ; aucune lecture
navigateur OpenRec validée. 124 tests passent et `git diff --check` passe.

Une campagne fraîche des 36 modèles a été lancée dans `source-audit-current`,
concurrence 4, délai 30 secondes, avec mise à jour des checks à la fin. Tant que
`summary.json` ne porte pas la révision courante, ne pas présenter cette campagne
comme achevée. Les anciens fichiers de ce répertoire sont conservés. Le triage
régénéré compte maintenant 21 familles avec modèle et 906 restantes.

### Campagne des 36 modèles terminée

Révision `18e124bea5abf917`, campagne réseau en 323,376 secondes : 26 modèles
renvoient des résultats, 5 demandent une authentification, 3 sont temporairement
indisponibles, 1 est vide et 1 média non pris en charge. Les 36 fichiers ont été
contrôlés contre la révision du moteur. `template_checks.json` est rafraîchi.
L'agrégation retient le meilleur état observé : des requêtes individuelles peuvent
encore échouer, notamment sur Bilibili. La recherche ne certifie pas la lecture.

125 tests passent. La reprise sans nouveau sondage a également été exécutée ; le
`summary.json` courant décrit cette reprise, et les fichiers par source conservent
les dates des observations réseau. Aucun déploiement effectué.

L'audit produit désormais `performance.json`, trié par durée cumulée des sondages
observés, en dédupliquant les scénarios réutilisés. Sur cette campagne : YouTube Music
142,038 s pour huit pages, Mail.ru 95,747 s pour huit pages, YouTubeSearch 74,048 s
pour douze pages. Ce ne sont pas les durées d'une recherche utilisateur ni des temps
muraux, puisque la campagne travaille en parallèle. Les campagnes fraîches futures
conservent automatiquement `summary-network.json` avant toute reprise ; une sélection
utilise ses propres fichiers suffixés pour ne pas écraser le bilan global.
La génération de ce rapport a été vérifiée par reprise, sans nouveau sondage réseau.

Les campagnes suivantes dans le même répertoire utilisent ces mesures pour lancer
les sources lentes en premier. Toutes les sources sélectionnées restent exécutées,
et le résumé conserve leur ordre habituel. Un rapport absent, invalide ou d'une
autre révision ne change pas l'ordre. Le gain de temps mural reste à mesurer lors
d'une future campagne fraîche ; il ne se déduit pas de la reprise en cache.
127 tests passent et la reprise des 36 modèles a été vérifiée avec cet ordonnanceur.

### Découverte ARTE

L'inspection des scripts de la page officielle `/fr/search/?q=nature` identifie
`https://api.arte.tv/api/emac/v4/fr/web/pages/SEARCH/?query=...&page=...`.
Sondages locaux conservés dans `arte-discovery.json` : nature pages 1 et 2,
piano page 1, témoin inexistant vide. La zone `listing_SEARCH` contient le catalogue,
la zone `boutique_SEARCH` est distincte et ne doit pas être importée.
Les pages renvoient 20 éléments mêlant programmes et collections ; les images
contiennent un marqueur `__SIZE__`. Ces adaptations restent à intégrer avant modèle.
Les données complètes de découverte restent dans `.local/arte-api.json` et les scripts
officiels dans `.local/arte-assets` ; le document partagé ne conserve que les champs utiles.
Attention : `page=2` sur l'endpoint de page répète les vingt résultats initiaux.
Il faut suivre le lien `pagination.links.next` de la zone ; ce second endpoint a été
sondé séparément. Ne pas publier un connecteur à numéro de page sur l'URL initiale.

### Modèle ARTE intégré

Le catalogue local compte maintenant 37 modèles, dont ARTE en français. La pagination
découvre le lien de première page dans la réponse, puis demande le bloc de 20 voulu,
sans figer l'identifiant de zone. Une fenêtre réelle de trois résultats à l'offset 18
franchit le changement de bloc. Les collections ARTE proposent le parcours d'épisodes ;
la collection Canada, la force de la nature retourne trois épisodes via le worker.
Preuve dans `source-audit-arte/collection.json`. Les vignettes à marqueur `__SIZE__`
restent omises ; la lecture navigateur reste non vérifiée.

129 tests passent, dont la découverte de pagination, la liste initiale vide et le refus
d'une URL privée. Les preuves des autres sources sont historiques après ce changement
du moteur. Aucun déploiement effectué.

Les vignettes ARTE remplacent maintenant le marqueur `__SIZE__` par `480x270` via
une substitution déclarative bornée ; le sondage réel répond HTTP 200 image/jpeg.
Le Québec boréal (112214-001-A) résout onze formats et des pistes de sous-titres,
consignés dans `source-audit-arte/resolve.json`. Cela ne valide pas encore la lecture
dans le navigateur. La collection miniature garde des épisodes « Sans titre » :
l'extracteur installé omet les métadonnées lors de ses `url_result`, à compléter.

Cette perte de métadonnées est maintenant corrigée par `app/arte.py`, qui conserve
les champs déjà téléchargés et enrichit uniquement les entrées sans titre. Le worker
réel affiche Le Québec boréal, Les prairies de l'Ouest et La forêt côtière du Pacifique
avec le titre de la série, dates, durées et vignettes. Les entrées de saisons déjà
enrichies par yt-dlp restent conservées. Un test traverse le worker et vérifie qu'une
seule requête suffit, avec date correctement normalisée pour yt-dlp.

Parcours ARTE vérifié dans le navigateur local isolé : recherche nature, collection
Canada, trois titres d'épisodes visibles, ouverture du Québec boréal. Lecture observée
à 7,854 s puis 28,438 s, paused=false et readyState=4 ; passage de 384×216 à 1280×720
après sélection 720p. Les sous-titres français sont sélectionnables ; leur affichage
sur les dialogues n'est pas encore certifié. Preuve bornée à cet épisode dans
`source-audit-arte/browser-playback.json`, sans validation globale de plateforme.

### Revalidation des 37 modèles

Après les corrections ARTE, les 132 tests passent. Une campagne réseau complète
est lancée sur les 37 modèles avec quatre workers, vers `source-audit-current`,
avec rafraîchissement des contrôles à sa terminaison. Tant qu'elle tourne, son
ancien résumé global ne constitue pas une preuve pour le moteur actuel.
Le triage régénéré dans `family-triage-next.json` compte 927 familles, 22 couvertes
et 905 restantes, dont 222 avec API visible et mention de recherche. Ce dernier
nombre est une présélection heuristique, pas un nombre de connecteurs réalisables.

Campagne terminée : 37 modèles en 307,314 s, moteur `835b7fae944a894a`,
25 avec résultats, 2 limités (Bilibili), 5 avec authentification requise,
3 temporairement indisponibles, 1 vide et 1 non pris en charge.
Les 37 fichiers individuels ont été contrôlés sur cette même révision.
La durée réseau est conservée dans `source-audit-current/summary-network.json`.

### Piste ARD

La page officielle `https://www.ardmediathek.de/suche/natur` expose
`https://api.ardmediathek.de/search-system/search/vods/ard`, avec `query`,
`pageNumber` commençant à zéro, `pageSize`, `platform=MEDIA_THEK` et
`sortingCriteria=SCORE_DESC`. Sondages dans `ard-discovery.json` : deux pages
de 24 vidéos pour natur, sans chevauchement, et 24 vidéos pour musik.
Le témoin inexistant renvoie néanmoins 12 vidéos (total annoncé 14) : comprendre
la recherche approchée ou les résultats de repli avant intégration. Le moteur
actuel commence ses pages à un ; ne pas l'utiliser tel quel pour cette API.
Aucun modèle ARD publié, aucune lecture ARD vérifiée.

ARD est maintenant intégré comme 38e modèle. La pagination accepte `first_page=0`,
avec valeur par défaut 1 pour les autres fournisseurs ; un test couvre la première
page et une fenêtre traversant deux blocs. Le sondage réel du connecteur à l'offset
22 retourne quatre vidéos à cheval sur les pages 0 et 1 (`ard-connector-probe.json`).
L'audit `source-audit-ard` confirme natur, musik, geschichte et l'accueil. La limite
sur les résultats sans correspondance exacte est explicitée dans le catalogue.
133 tests passent. La lecture ARD reste non vérifiée. Le changement de pagination
modifie le moteur : la campagne des 37 modèles précédente reste historique.

Deux résultats ARD ont ensuite été résolus par le worker avec sa protection réseau :
Kikaninchen und die tierisch tolle Natur (8 formats HTTPS/HLS) et Sardinien · Arche
aus Stein (9 formats HTTPS/HLS, sous-titres deu). Les observations datées et liées
au moteur figurent dans `source-audit-ard/resolve.json`. L'instance navigateur isolée
n'a pas encore ARD activé ; aucune lecture navigateur ARD n'est revendiquée.

ARD activé ensuite dans l'instance locale isolée : recherche natur, ouverture de
Sardinien, lecture à 8,588 s en 480×270 puis 19,631 s en 1280×720, paused=false,
readyState=4. Preuve : `source-audit-ard/browser-playback.json`. Le démarrage a
subi plusieurs HEAD 502 avant des GET 200 : latence à diagnostiquer. La piste deu
résolue n'apparaît pas dans le sélecteur de sous-titres ; ne pas la déclarer lisible.

Diagnostic suivant : le lecteur adaptatif ignorait `result.subtitles`, contrairement
au lecteur de fichier direct. Il ajoute désormais les pistes VTT externes à Shaka
après chargement, via le même relais. Les 133 tests passent. Les HEAD sur le manifeste
ARD réussissent au nouveau sondage direct et via worker ; l'échec intermittent
observé dans le navigateur n'est pas encore reproduit ni corrigé.

Validation navigateur des VTT : après expiration du premier chargement, la nouvelle
tentative réussit. La piste deu est proposée et ses sous-titres sont visibles sur
Sardinien à 18,435 s, paused=false, readyState=4. Preuve datée dans
`source-audit-ard/browser-subtitles.json`. Le correctif est donc vérifié sur cette
vidéo. La cause du délai initial reste ouverte ; le serveur répondait au contrôle
HTTP de santé de session en 10 ms et aucun worker média n'était encore actif.

Le mode `--summarize-only` refuse maintenant les preuves manquantes ou provenant
de moteurs/environnements différents, au lieu de présenter silencieusement un
bilan partiel ou une révision trompeuse. Il ne réécrit plus les preuves individuelles.
Un test vérifie le refus et la préservation des fichiers ; 134 tests passent.

### Piste Télé-Québec

`video.telequebec.tv` redirige vers `telequebec.tv`. Les assets relatifs doivent
être chargés sur ce dernier hôte : l'ancien renvoie la page HTML à leur place.
La page de recherche utilise `https://api.pc-cms.tele.quebec/graphql` et
`searchPage(keywords, resultDefinitions)` avec ROOT_PRODUCTS et PLAYABLE_EPISODES.
Une requête publique réduite pour nature répond avec des blocs SEARCH_RESULTS ;
preuve dans `telequebec-discovery.json`. Les fragments de résultats et la pagination
restent à examiner avant connecteur. Assets officiels conservés localement dans
`.local/telequebec-assets`, notamment search-B5byn624.js et son import blocks-BNMkyBVh.js.

Le fragment officiel ArtisanBlocksSearchResults expose les épisodes dans
blockConfiguration.entries : id, titre, durée, saison, épisode et slug de collection.
Le sondage nature retourne trois épisodes et totalEntries=180. Les routes officielles
de lecture sont désormais `/regarder/{collection}/{saison}/{episode}`. Le worker
installé échoue sur `/regarder/cochon-dingue/6/29` (temporarily_unavailable) ; les
extracteurs Télé-Québec installés visent surtout les anciennes URLs. Résultats conservés
dans `telequebec-discovery.json`. Une adaptation de lecture reste nécessaire avant
de prétendre cette nouvelle interface prise en charge.

### Campagne actuelle de 38 modèles

Campagne terminée en 302,635 s, moteur `694f559bfd8be29e`. Les 38 fichiers
individuels correspondent à cette révision : 27 modèles avec résultats,
1 limité, 1 vide, 5 nécessitant une authentification, 3 temporairement
indisponibles et 1 non pris en charge. Contrôles du catalogue rafraîchis.
La mesure avant reprise est conservée dans `source-audit-current/summary-campaign.json`
(lancement avec --resume, mais les changements de moteur imposaient les sondages).
YouTube Music représente 147,847 s cumulées pour huit pages, Mail.ru 85,941 s
pour huit pages et YoutubeSearch 66,963 s pour douze pages. Ces durées cumulées
ne sont ni la durée murale du lot, ni celle d'une recherche utilisateur.

Télé-Québec, diagnostic précisé : TeleQuebecEmission échoue à extraire le media id
du nouveau HTML. Le script officiel conserve le compte Brightcove 6150020952001,
le player ja7RtbSne et, pour Cochon dingue S6E29, videoId=ref:100620910. L'extracteur
Brightcove atteint ce lecteur mais reçoit « Access to this resource is forbidden by
access policy ». Observation bornée à cet épisode, consignée dans la découverte.
La famille est mise en attente dans le triage ; pas de contournement ni de nouvelle
compatibilité de lecture revendiquée.

### CBS News intégré

39 modèles au catalogue. L'adaptateur officiel CBS News utilise Queryly avec une
clé publique de site, le filtre contenttype=video, batchsize et endindex (offset).
Deux pages nature ont trois résultats distincts chacune ; science répond et le
témoin inexistant est vide (`cbs-discovery.json`). Le modèle déclaratif réutilise
le moteur existant sans changer sa révision. L'audit `source-audit-cbs` confirme
nature, science, music et l'accueil. Nature: Newfoundland résout six formats via
le worker ; aucune lecture navigateur CBS News n'est encore vérifiée.
134 tests passent. Les preuves des 38 autres modèles restent sur le moteur actuel.

Lecture CBS News observée dans l'instance locale isolée, média ouvert par URL :
Nature: Newfoundland progresse de 3,066 à 14,857 s, paused=false, readyState=4,
1280×720 après sélection 720p. Preuve `source-audit-cbs/browser-playback.json`.
Cet essai ne vérifie ni le téléchargement, ni l'ensemble du catalogue CBS.

### Piste NPO

La page officielle `https://npo.nl/start/zoeken` utilise une route
`/api/domain/search-collection-items`. Le composant transmet searchQuery, searchType,
des filtres et des paramètres de profil à un sérialiseur (module client 71220).
Le premier sondage avec searchQuery et searchType seuls répond 404 : ce n'est pas
une preuve qu'un compte est requis. Il faut vérifier la sérialisation et le chemin
effectif avant de poursuivre. Observation dans `npo-discovery.json`, scripts dans
`.local/npo-assets` (composant 5075). Aucun modèle NPO ajouté ni blocage global conclu.

Le sérialiseur 71220 est identifié : URLSearchParams avec partyId, searchQuery,
searchType, subscriptionType et includePremiumContent, puis filtres et profil
optionnels. Un second appel avec PROGRAM, ANONYMOUS et includePremiumContent=false
répond encore 404. Le contexte partyId du profil anonyme reste non établi. Piste
mise en attente pour reprise par observation réseau du site officiel ; aucune
exigence de compte n'est démontrée. Les essais sont conservés dans npo-discovery.json.

Observation navigateur suivante : sans connexion, la recherche natuur sur le site
officiel affiche des séries et dix épisodes, avec bouton Toon meer afleveringen.
NPO est retiré des pistes bloquées : les 404 des sondages directs ne reproduisent
pas le contexte réseau du site. Onglet de recherche et exemples de liens conservés
dans `npo-discovery.json`. Recherche anonyme confirmée ; connecteur et lecture
AnyTube toujours à implémenter et vérifier.

Capture réseau réussie : searchType=broadcasts (épisodes) ou series, et
subscriptionType=anonymous en minuscules. Le rejeu direct avec broadcasts et
includePremiumContent=true répond 200 sans partyId ni compte. Les anciens essais
utilisaient de mauvaises valeurs d'énumération. La réponse contient items avec
productId, slug, titre, durée et restrictions. Requête exacte et échantillon public
ajoutés à `npo-discovery.json` ; réponse complète locale dans npo-correct-search.json.

Le test de lecture du lien muziekfeest-op-het-plein_15 échoue dans NPOIE :
l'extracteur interroge l'ancien service npostart.nl/player avec le slug comme id,
puis échoue à parser le JSON. Une éventuelle intégration de recherche doit donc
annoncer cette limite et rester bornée aux 50 résultats effectivement reçus,
tant que la pagination au-delà de ce bloc n'est pas vérifiée. La tentative d'ajout
du modèle par commande a été rejetée par le contrôle automatique ; aucun modèle
NPO n'a été ajouté lors de cette tentative.
