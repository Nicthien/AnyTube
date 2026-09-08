# AnyTube 0.6.0-preview — bilan de validation

## Français

Cette livraison ajoute Chromium interactif, des sessions chiffrées et un trajet sortant sélectionné par l’administrateur. Aucun site public particulier n’est déclaré compatible. Le VPN reste désactivé et le trajet Direct est conservé lors de la livraison.

### Contrôles effectués

- 260 tests Python sur Windows : réussite (15,739 s). Un test de fermeture de socket a présenté une erreur Windows intermittente `WinError 64` lors d’une exécution précédente ; la suite complète suivante passe. La même suite passe dans l’image Linux finale : 260 tests en 211,969 s.
- Syntaxe de tous les fichiers JavaScript, garde-fou contre les dialogues natifs et `git diff --check`.
- Fixtures HTML, JSON, Chromium, ajout partiel, export ZIP, échec sans ajout, annulation et réouverture ; interface à 390 et 1400 pixels, clavier, thèmes clair/sombre.
- Session interactive réelle : diffusion CDP relayée, clic manuel sur une fixture neutre, cookies après redirection, restauration du stockage, téléversement d’un PDF de test, suppression, affichage mobile. Aucun clic automatique sur une vérification réelle.
- Parcours accès requis → budget suspendu → session explicitement validée → reprise → source ajoutée → recherche normale, vérifié par test déterministe.
- Conteneurs intégrés avec pare-feu et sandbox Chromium : ouverture et sauvegarde d’une session ; proxy indisponible sans repli ; interface encore accessible ; retour explicite à Direct.
- Tunnels réels WireGuard et OpenVPN vers des serveurs de test éphémères : résolution publique HTTPS par le tunnel, CONNECT avec IP imposée, recherche JSON, extraction yt-dlp, téléchargement HLS, miniature, sous-titres, MP4, segments et réécriture HLS/DASH. Les deux tunnels interrompus rendent les requêtes de contrôle impossibles, sans basculement direct.
- Browserless existant : image sans Chromium local et parcours d’observation testés séparément avant bascule.

Le Docker Desktop local étant indisponible, les conteneurs de recette utilisent des réseaux et données temporaires sur Unraid. Ils ne montent pas les données de production. Les certificats et clés VPN de test sont éphémères et supprimés après les essais.

### Mesures des fixtures de découverte

| Parcours | Résultat | Durée |
| --- | --- | --- |
| HTML | ajout | 1,306 s, 16 requêtes HTTP |
| JSON | ajout | 0,281 s |
| Pages mixtes | ajout partiel explicite | 0,293 s |
| Sélecteurs incomplets | sans ajout | 0,081 s |
| Recommandations variables | sans ajout | 0,080 s |
| HTML rendu | ajout | 12,539 s |
| Page d’erreur rendue | sans ajout | 2,123 s |

Ces mesures correspondent à des fixtures contrôlées, sans édition manuelle du connecteur. Deux parcours de session réseau intégrée ont aussi vérifié le blocage d’un proxy arrêté. Ils ne mesurent pas le délai d’une vérification humaine réelle.

### Reproduire

Consulter les scripts `check-source-diagnostics.py`, `check-source-diagnostics-ui.py`, `check-interactive-browser.py` et `check-integrated-stack.py`. Ce dernier est réservé au conteneur jetable avec `ANYTUBE_ENVIRONMENT=validation-060`.

Sur un hôte Linux Docker isolé, `ANYTUBE_TEST_OUTPUT=/chemin/absolu/logs bash scripts/check-vpn-containers.sh` construit son serveur de test et utilise l’image `anytube:0.6.0-preview` (surcharge `ANYTUBE_TEST_IMAGE`). Le sous-réseau `172.30.91.0/24` doit être libre. Le script échoue si ses noms de réseau/conteneurs existent déjà ; il ne faut pas l’exécuter en parallèle avec lui-même. Les fichiers média sont des couleurs et un son générés par FFmpeg.

### Limites

Aucun fournisseur VPN personnel n’a été configuré ni testé. La recette contrôle les chemins exercés et leur panne ; elle n’est pas une certification universelle de fuite réseau. Les résolutions DNS publiques passent par HTTPS dans le proxy/VPN ; le nom interne de la passerelle Chromium est résolu au démarrage avant fermeture des sorties DNS du navigateur.

Caméra, microphone, WebSockets des sites, fenêtres secondaires, `sessionStorage` et redirections exigeant la retransmission d’un téléversement ne sont pas pris en charge. Le stockage JavaScript n’est pas utilisable automatiquement par yt-dlp. Une vérification d’âge ou une connexion peut donc rester impossible malgré un navigateur fonctionnel. Recherche, reconnaissance des pages et lecture restent des preuves distinctes.

## English

0.6.0 adds an isolated interactive Chromium service, encrypted owner-bound sessions and administrator-selected outgoing routing. It does not claim compatibility with a particular public site. Direct remains selected; no personal VPN provider is enabled.

Validation covers 260 Python tests, JavaScript syntax and the native-dialog guard, HTML/JSON/rendered discovery fixtures, partial acceptance, ZIP export, cancellation, reopening, keyboard, mobile and both themes. Actual CDP interaction, cookie/storage restoration and a neutral PDF upload are tested. The integrated container firewall/sandbox and unavailable-proxy behavior are checked separately.

Real ephemeral WireGuard and OpenVPN servers exercise pinned CONNECT, public DNS over HTTPS, search, extraction, HLS download, thumbnails, subtitles and HLS/DASH media rewriting. Both outage checks fail closed. These tests use isolated Unraid containers because local Docker is unavailable. They neither test the user's VPN provider nor certify every possible traffic pattern.

See the French table for fixture timings and the bilingual interactive-network guides for configuration and unsupported browser features. The final Linux suite passes all 260 tests (211.969 s); Browserless is checked separately before deployment. The durable deployment record adds the commit, archive verification and backup location.
