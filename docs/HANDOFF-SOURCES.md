# Passation — extension des sources AnyTube

> Suite du chantier : voir `SOURCES-NEXT.md`. Les onze modèles ajoutés depuis cette
> passation sont dans `app/search_templates.json` ; leurs données sont séparées du
> hash du moteur, tandis que leur configuration effective reste signée. L'audit dispose
> désormais de reprises par scénario, de durées et d'une concurrence configurable.
> Les chiffres et commandes détaillés ci-dessous décrivent l'état de la passation initiale.

Note de reprise pour un agent qui continue le chantier des sources. Écrite le 6 septembre 2026,
dépôt `C:\DEV\Projects\AnyTube`, branche `main`, rien n'est poussé.

Lire d'abord `AGENTS.md`, puis `docs/SOURCES-PROGRESS.md`, `docs/sources-lot-01.md` et
`docs/sources-lot-02.md`. Ce fichier ne répète pas leur contenu : il donne l'état, les mesures
déjà faites, les pièges, et les chantiers suivants.

## 1. État

Les **31 modèles de recherche** du catalogue sont examinés et corrigés (lots 01 et 02). Preuves
datées par modèle dans `docs/source-audit-lot-01/` et `docs/source-audit-lot-02/`.

Sur ces 31, au dernier sondage : 20 renvoient des résultats, 5 attendent un compte (PRX ×4,
Vimeo), 3 sont cassés en amont (Google Vidéos, Yahoo Vidéos, Rokfin), 1 est filtré par
intermittence (Bilibili, HTTP 412), 1 est vide (Google Vidéos) et 1 n'est pas lisible par
conception (VR SQUARE, réservé à l'application du fournisseur).

**Lecture, audio, direct, sous-titres et téléchargement restent non vérifiés pour les 31.** Un
essai de recherche ne les valide jamais. Aucune plateforme n'est déclarée revue ni vérifiée dans
son ensemble (`reviewed_platforms = 0`, `verified_platforms = 0`).

## 2. Mesures déjà faites — ne pas les refaire

| Question | Réponse mesurée |
| --- | --- |
| Familles inférées au total | 927 |
| Familles sans modèle de recherche | 911 |
| … avec une API JSON à hôte fixe visible dans le code amont | **407** |
| … et mentionnant en plus une recherche | **233** |
| Classes `SearchInfoExtractor` de yt-dlp | 10, **toutes déjà exploitées** |
| Classes de recherche par URL encore inutilisées | **2** (`CiscoLiveSearch`, `OpenRecChannelSearch`) |
| Coût de démarrage d'une sonde (import yt-dlp compris) | 0,45 s — **l'outillage n'est pas le goulot** |
| Instances PeerTube reconnues par l'extracteur installé | 1 292 |

Conséquence : le backlog réaliste est de l'ordre de **200 à 230 familles**, pas 911. Et il n'y a
plus de gisement gratuit : chaque nouveau modèle demande d'écrire son connecteur.

`python scripts/triage_families.py --limit 40 --output docs/family-triage.json` régénère le
classement. Têtes de liste au 6 septembre : `rutube`, `nhk`, `radiofrance`, `orf`, `rtve`, `npo`,
`nrk`, `qqmusic`, `rai`, `skyit`.

## 3. Pièges du dépôt

**La révision du moteur périme les preuves.** `engine_version()` (dans `app/verification.py`)
hache `connectors.py`, `worker.py`, `catalog.py`, `pagination.py`, `verification.py`, `registry.py`,
`vault.py`, `failures.py`, `adapters.py`, `access.py`, `discovery.py`, `relay.py`, `playback.py`,
`main.py`, `library.py`, `egress.py` et deux fichiers statiques. **Toute modification d'un de ces
fichiers — y compris un commentaire déplacé — change la révision et rend obsolètes toutes les
preuves enregistrées.**

Règle de travail qui coûte le plus cher à ignorer : **grouper toutes les modifications de code,
puis lancer une seule campagne de preuves.** Cela a été payé trois fois.

`app/inventory.py`, `scripts/` et `tests/` ne sont **pas** couverts : ils peuvent bouger sans
périmer les preuves.

**Autres pièges rencontrés :**

- `parse_qsl` supprime les paramètres vides ; utiliser `keep_blank_values=True` partout où une URL
  est reconstruite (trois endroits l'utilisent déjà).
- yt-dlp lève `yt_dlp.networking.exceptions.HTTPError`, qui **n'hérite pas** de
  `urllib.error.HTTPError`. `app/failures.py` gère les deux ; ne pas régresser.
- Un 412 d'un fournisseur est un filtrage anti-robot, pas une précondition : AnyTube n'envoie
  jamais d'en-tête conditionnel.
- Les tests de `tests/` ne doivent **jamais** ouvrir de connexion sortante ; les essais réseau
  vivent dans `scripts/audit_lot.py`.
- Aucun dialogue JavaScript natif (`alert`, `confirm`, `prompt`) : garde-fou dans
  `tests/test_bootstrap.py`.

## 4. Chantiers suivants, par rentabilité

### 4.1 Étendre la déclinaison par instance aux autres logiciels fédérés

Le mécanisme existe déjà et est testé : `app/catalog.py::INSTANCE_SOFTWARE`,
`app/connectors.py::instance_host`, `POST /api/sources` avec `instance`. Un seul logiciel est
déclaré (PeerTube). Ajouter un logiciel demande : un connecteur JSON pour son API, une entrée dans
`INSTANCE_SOFTWARE` avec son `probe_url`, et des essais.

Candidats à examiner : Invidious, Piped, MediaCMS, Owncast, Misskey, Funkwhale. **Vérifier d'abord
que l'extracteur installé reconnaît des instances**, sinon la recherche marchera sans la lecture —
ce qui reste acceptable mais doit être annoncé, comme pour PeerTube.

### 4.2 Un échafaudage de connecteur

Aujourd'hui `scripts/audit_lot.py --template X` sonde et écrit les preuves ; la moitié amont
manque. Ce qu'il faudrait : à partir d'une famille et d'une URL d'API, émettre un connecteur
candidat, deviner la correspondance des champs depuis une réponse réelle, puis enchaîner sur la
sonde. Les briques existent : `POST /api/connectors/test`, `Connector`, `pointer()`.

### 4.3 Filtres de durée et de date au-delà de Dailymotion

Bloqué par une question de conception, pas de volume. Les classements ont pu devenir déclaratifs
parce qu'un classement est **une URL entière** ; deux URL complètes ne se composent pas (durée
**et** date **et** classement). Il faut décrire des **paramètres** — nom, valeur, et un
emplacement pour un horodatage calculé — au lieu d'URL complètes. Niconico
(`filters[lengthSeconds][gte]`) et archive.org exposent déjà ces filtres.

### 4.4 Débloquer les cinq modèles qui attendent un compte

PRX ×4 et Vimeo : le chemin par jeton de coffre est en place mais **n'a jamais été essayé**. Le
format des résultats PRX vient du code de l'extracteur, pas d'une réponse observée. Il faut un
compte déposé dans le coffre — **ne jamais demander de secret dans la conversation**.

### 4.5 Petits restes identifiés

- `BiliBiliSearch` et `DailymotionSearch` s'affichent avec le nom brut de leur extracteur : ajouter
  une entrée dans `catalog.REVIEWED` (cosmétique, mais change la révision du moteur).
- `capabilities()['home_kind']` est calculé sur la configuration stockée sans passer par la
  correction du validateur : une source ancienne peut y annoncer `feed` à tort. Le libellé montré
  au lecteur (`/api/home`, champ `feed_kind`) est correct.
- `PeerTubePlaylist` sert la recherche vidéo de PeerTube ; la recherche de listes de lecture
  (`search/video-playlists`) demanderait de relier les résultats au navigateur de collections
  plutôt qu'à la lecture.
- Concurrence de la campagne fixée à 2 dans `scripts/audit_lot.py` ; des plateformes différentes
  ne partagent pas leurs quotas et un verrou par plateforme existe déjà côté `run_worker`.

## 5. Règles à respecter

- API officielles d'abord, fonctions yt-dlp ensuite.
- Aucun code exécutable dans les modèles : tout est déclaratif et validé.
- Aucun secret dans le code, les rapports, les exports ou les journaux ; utiliser le coffre.
- Ne contourner ni DRM ni restriction d'accès.
- Distinguer toujours : **disponibilité technique**, **implémentation**, **vérification**. Un
  compte manquant ou une panne temporaire n'est ni une réussite ni une impossibilité définitive.
- Un résultat vide n'est pas une preuve d'échec : essayer une requête adaptée à la plateforme
  (c'est ainsi que VR SQUARE a été compris).
- Ne pas présenter le catalogue comme terminé.

## 6. Commandes

```bash
python -m unittest discover -s tests     # 96 tests déterministes, aucun réseau
git diff --check
python scripts/triage_families.py --limit 40 --output docs/family-triage.json
python scripts/audit_lot.py --batch all                       # campagne complète
python scripts/audit_lot.py --template PeerTube --instance tilvids.com
python scripts/audit_lot.py --batch lot-01 --summarize-only   # verdict sans réseau
python scripts/audit_lot.py --batch lot-01 --update-checks    # rafraîchit template_checks.json
```

Environnement : `.venv` du projet, Python 3.14, yt-dlp 2026.08.19. Le Python global n'a pas
yt-dlp. Ne pas déployer sur Unraid et ne rien pousser sans demande explicite.
