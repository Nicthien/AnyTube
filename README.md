# AnyTube

**Français** · [English](README.en.md)

Plateforme vidéo personnelle auto-hébergée : réunir ses sources, rechercher des vidéos, les lire et conserver ses médias dans une bibliothèque privée.

**Statut : version de développement · 0.3.0-preview.** Les capacités dépendent de chaque source et les validations restent partielles. Un extracteur installé ne garantit ni la recherche, ni la lecture, ni le téléchargement.

[![Licence MIT](https://img.shields.io/badge/Licence-MIT-blue.svg)](LICENSE)
[![Soutenir sur Ko-fi](https://img.shields.io/badge/Soutenir-Ko--fi-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/nthstudio)

Ce projet est développé sur mon temps libre. Si vous souhaitez le soutenir, vous pouvez m'offrir un [Ko-fi](https://ko-fi.com/nthstudio). Merci !

## Fonctionnalités

- **Explorer ses sources** : accueil par source, recherche fédérée, sélection multiple, classements et chargement supplémentaire selon les connecteurs. Les erreurs d'une source ne masquent pas les autres résultats.
- **Configurer ses connecteurs** : catalogue yt-dlp, modèles de recherche, API JSON GET/POST, sources par URL, copie et test d'une configuration avant enregistrement.
- **Lire ses vidéos** : lecteur servi localement, résolution des médias, relais privé HLS/DASH, sélection des qualités et pistes proposées. Ces parcours restent expérimentaux selon la plateforme et le navigateur.
- **Conserver ses médias** : préparation MP4 H.264/AAC ou audio M4A, progression, annulation, nouvelle tentative, bibliothèque persistante et quotas administrables.
- **Retrouver son activité** : favoris, historique, reprise et préférences privés par compte ; navigation dans les collections et file de lecture.
- **Partager son installation** : premier administrateur par jeton unique, comptes sur invitation, sessions révocables et séparation des données par utilisateur.
- **Gérer les accès aux sources** : coffre chiffré pour clés API, jetons bearer et cookies importés, avec domaines autorisés et références distinctes pour la recherche et le média.
- **Adapter l'interface** : mobile et ordinateur, thèmes clair/sombre, confirmations intégrées et option SponsorBlock pour YouTube. L'interface est actuellement en français.

AnyTube ne charge pas de lecteur embarqué des plateformes ni de script publicitaire tiers. Les vignettes sont demandées directement aux plateformes par le navigateur. SponsorBlock utilise des contributions communautaires et ne garantit pas la suppression de toute publicité.

## Installer avec Docker

Prérequis : Git, Docker Engine avec conteneurs Linux et Docker Compose v2. Le noyau doit prendre en charge `iptables` et le filtrage par propriétaire ; voir le [guide Unraid](docs/UNRAID.md).

```sh
git clone https://github.com/Nicthien/AnyTube.git
cd AnyTube
cp .env.example .env
docker compose -f compose.unraid.yaml up -d --build
docker compose -f compose.unraid.yaml logs --tail=100 anytube
```

Sous PowerShell, remplacer `cp .env.example .env` par `Copy-Item .env.example .env`.

Ouvrir [localhost:8088](http://localhost:8088), puis créer le premier administrateur avec le jeton à usage unique affiché dans les journaux. Les comptes suivants sont créés sur invitation depuis **Mon compte**.

L'image `anytube:family` est construite localement ; aucune image AnyTube publiée dans un registre n'est requise. Un seul conteneur regroupe l'application, le proxy sortant et les sauvegardes quotidiennes. Python, yt-dlp, FFmpeg, ffprobe et Node sont inclus.

### Configuration

Copier `.env.example` est nécessaire pour utiliser les chemins locaux du démarrage rapide. Sans ce fichier, Compose utilise les chemins Unraid par défaut.

| Variable | Valeur dans `.env.example` | Rôle |
| --- | --- | --- |
| `ANYTUBE_BIND` | `127.0.0.1` | Adresse d'écoute ; `0.0.0.0` pour le réseau local. |
| `ANYTUBE_PORT` | `8088` | Port HTTP. |
| `ANYTUBE_APPDATA` | `./data/docker` | Base SQLite et sauvegardes. |
| `ANYTUBE_STORAGE` | `./data/media` | Cache et bibliothèque média. |
| `ANYTUBE_SECRETS` | `./secrets/docker` | Clé du coffre, séparée de la base. |
| `ANYTUBE_PUBLIC_URL` | vide | URL HTTPS canonique, après configuration du reverse proxy. |

Pour Unraid, adapter les chemins vers `/mnt/user/appdata/anytube`, `/mnt/user/anytube` et `/mnt/user/appdata/anytube-secrets`. Pour un accès LAN, ouvrir `http://IP_DU_SERVEUR:8088` après modification de `ANYTUBE_BIND`.

Lorsqu'une URL HTTPS est configurée, les cookies deviennent sécurisés et les autres adresses redirigent vers cette URL. La connexion doit alors passer par HTTPS.

Le conteneur prépare ses volumes et son pare-feu au démarrage, puis exécute les services applicatifs sous des utilisateurs dédiés sans capacités. Le proxy sortant et le pare-feu limitent l'accès aux adresses publiques. Le fichier historique `compose.yaml` est réservé au développement et ne fournit pas cette isolation réseau.

### Sauvegardes et mises à jour

SQLite conserve comptes, sources, préférences, tâches et réglages. Les sauvegardes quotidiennes conservent sept copies de la base et une archive de configuration. Sauvegarder également la bibliothèque média et **une copie privée séparée de la clé du coffre** : la base seule ne permet pas de restaurer les accès chiffrés.

Avant une mise à jour, conserver le code, l'image et une sauvegarde cohérente. Les procédures de restauration sont détaillées dans [docs/UNRAID.md](docs/UNRAID.md).

## Sources et compatibilité

AnyTube distingue trois capacités : **extraire une URL**, **rechercher sur une plateforme** et **lire un média dans le navigateur**. Chacune nécessite sa propre vérification.

L'inventaire du 6 septembre 2026 répertorie 1 750 extracteurs, regroupés automatiquement en 927 familles, et 31 modèles de recherche. Ces nombres décrivent le catalogue et ne représentent pas des plateformes certifiées compatibles.

Dans **Mes sources**, ajouter un modèle ou créer un connecteur, tester sa configuration, puis l'enregistrer. Les API JSON utilisent des chemins JSON Pointer (`/data/videos`, `/title`, `/owner/name`) ; la pagination et les classements dépendent de l'API. Les sources « URL uniquement » ne fournissent pas de recherche.

Les **31 modèles de recherche** ont été examinés par lots, plateforme par plateforme, en lisant les interfaces officielles et le code des extracteurs installés, puis en sondant chaque modèle avec trois requêtes adaptées sur deux pages : [lot 01](docs/sources-lot-01.md) (20 modèles) et [lot 02](docs/sources-lot-02.md) (11 modèles). Un modèle examiné ne rend pas sa plateforme vérifiée : **1 719 extracteurs installés n'ont toujours aucun modèle de recherche**, et la lecture, l'audio, le direct, les sous-titres et le téléchargement restent non vérifiés pour ces 31 modèles.

Trois modèles sont inutilisables pour une cause identifiée chez le fournisseur ou dans l'extracteur amont (Google Vidéos, Yahoo Vidéos, Rokfin) et cinq attendent un compte déposé dans le coffre (les quatre modèles PRX et Vimeo). Le catalogue affiche ces limites à côté de chaque modèle.

Les preuves datées sont consignées dans [l'état des sources](docs/SOURCES-PROGRESS.md). Les essais documentés comprennent une recherche Dailymotion, la lecture HLS de Big Buck Bunny dans Chrome et la préparation vidéo/audio de ce film. Ils ne valident pas toutes les plateformes ni toutes les révisions ultérieures du code.

### Limites actuelles

- DASH réel, direct, changements de langues/sous-titres, Firefox, Safari et lecture authentifiée auprès d'une plateforme restent à vérifier.
- Pas de contournement des DRM ; OAuth et les formulaires de connexion propres aux plateformes ne sont pas implémentés.
- Certains connecteurs rechargent un préfixe de résultats, limité à 100 par source, au lieu d'utiliser une pagination native. Une plateforme dont l'ordre change entre deux appels peut alors répéter des résultats en page suivante ; l'interface les élimine, elle ne les invente pas.
- Les filtres de durée et de date ne sont disponibles que sur Dailymotion. Les classements de recherche et d'accueil dépendent de chaque modèle.
- La prise en charge des formats, segments volumineux, reprises réseau et files persistantes reste incomplète. Les sites peuvent refuser l'extraction ou demander une authentification.
- Les nouvelles capacités média et d'accès aux sources ne sont pas toutes validées sur Unraid. Consulter les rapports avant de les considérer comme disponibles sur une installation existante.

## Développement

Le Dockerfile utilise Python 3.14 et Node 24. Pour les traitements média hors Docker, installer également FFmpeg/ffprobe et Node sur l'hôte.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m unittest discover -s tests
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8088
```

Pour activer le coffre en développement, créer sa clé une seule fois avant de lancer le serveur :

```powershell
.\.venv\Scripts\python scripts/init_vault.py secrets/vault.key
$env:ANYTUBE_VAULT_KEY_FILE = (Resolve-Path secrets/vault.key).Path
```

Réutiliser cette clé aux démarrages suivants. Ne jamais remplacer une clé nécessaire à des accès existants.

Shaka Player est déjà livré dans `app/static/vendor/`. Pour régénérer les fichiers après une mise à jour de dépendance :

```sh
npm ci
npm run vendor
```

API : `/api/health`, `/api/sources`, `/api/catalog` et schéma `/openapi.json`. Les mutations et recherches POST exigent `X-AnyTube: 1` ; les routes privées exigent aussi une session.

Lancer un seul processus Uvicorn : certaines tâches, sessions de lecture et réservations de quotas sont coordonnées en mémoire.

## Contribuer

Les [issues](https://github.com/Nicthien/AnyTube/issues) et pull requests sont les bienvenues. Pour un problème de source, préciser la fonction, les versions et un exemple public reproductible, sans partager de cookies, jetons ou données de compte.

Avant de proposer une modification, lancer `python -m unittest discover -s tests` dans l'environnement du projet et `git diff --check`. La suite comprend un garde-fou contre les dialogues JavaScript natifs. Une modification de connecteur ou de lecture demande aussi un essai réel de la capacité annoncée.

## Documentation

- [Installation, exploitation et restauration Unraid](docs/UNRAID.md) — français.
- [État des sources, preuves et travaux restants](docs/SOURCES-PROGRESS.md) — français.
- [Lot 01 des modèles de recherche](docs/sources-lot-01.md) et [lot 02](docs/sources-lot-02.md) — français ; corrections, preuves datées et blocages restants.
- [Historique de validation du socle familial](docs/FAMILY-DELIVERY.md) — français ; certains constats précèdent l'extension des sources.

## Licence

Le code original d'AnyTube est distribué sous [licence MIT](LICENSE), © 2026 Nicolas Thiennet.

Les dépendances et données tierces conservent leurs licences respectives, notamment [Shaka Player sous Apache-2.0](app/static/vendor/shaka-player.LICENSE). Les données SponsorBlock sont attribuées dans l'interface sous CC BY-NC-SA 4.0. La licence du projet ne confère aucun droit sur les médias des plateformes.
