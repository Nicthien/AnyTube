# Assistant de découverte des sources

## Recherche HTML et exemples (0.5.0-preview)

« Aider la détection » accepte jusqu’à cinq URL de vidéos et une URL de recherche
avec son terme. Deux exemples du même site aident à distinguer les pages vidéo.
Les exemples externes restent des indices et n’autorisent pas un autre domaine.
Les deux recherches de contrôle sont indépendantes de ces exemples.

Le nouveau connecteur `html` décrit des sélecteurs CSS simples et le chargement
`http` ou `chromium`. Le backend extrait titres, liens, vignettes et durées sans
exécuter de code généré. Les liens relatifs et durées textuelles sont normalisés.
Les pseudo-classes CSS et scripts personnalisés sont refusés. La pagination utilise
un lien suivant ou un numéro de page ; sans pagination validée, seule la première
page est annoncée. Une recherche HTML est plafonnée à 100 résultats et dix pages.

Les recherches HTML doivent être reproductibles par une URL GET. Les formulaires
POST, CAPTCHA, connexions, défilement infini et interactions spécifiques ne sont
pas automatiquement transformés en connecteurs. Une source « Navigateur requis »
utilise la passerelle à chaque recherche : sa disponibilité est nécessaire aussi
après la découverte. Browserless direct reste incompatible avec le champ de
configuration ; conserver la passerelle AnyTube `http://source-browser:8010`.

Avant ajout, deux recherches, un témoin improbable et la pagination sont contrôlés.
Pour le HTML, toutes les URL vidéo des deux échantillons doivent également exposer
une balise vidéo ou des métadonnées Open Graph/VideoObject. Une absence de preuve
conserve un brouillon ; la lecture, les collections et l’extraction restent non
vérifiées. Trois nouveaux candidats au maximum, deux corrections au total.

« Ajouter des exemples et reprendre » crée une tentative liée à la précédente.
Les pages et preuves sont rechargées, aucune preuve périmée ne déclenche un ajout.
La reprise conserve propriétaire, réglages, exemples et comparaison de source.
Les anciennes tâches restent lisibles et expirent après trente jours.

API : les champs facultatifs `video_examples`, `search_example_url` et
`search_example_query` complètent `POST /api/source-assistant/jobs`.
`POST /api/source-assistant/jobs/{id}/resume` accepte ces trois champs et `minutes`.
Une liste fournie remplace les exemples antérieurs ; l’interface les préremplit.
Les tâches actives et les choix de domaine ne peuvent pas être repris.

Les documents HTML et réponses réseau sont bornés à 2 Mo, les documents analysés
à 20 000 éléments, les sélecteurs à 200 caractères. Le navigateur ne conserve pas
de profil ; ses requêtes passent toujours par le contrôle réseau public. Les
secrets des services restent dans le backend et ne sont pas remis aux extracteurs.

Recette reproductible du navigateur : `scripts/check-html-browser.py`, dans
l’image d’observation avec les tests montés et les dépendances de test installées.
Le script utilise un site simulé dans une vraie session Chromium isolée et une
base temporaire, puis vérifie découverte, ajout et recherche via l’API normale.
Il ne modifie aucune source de production.

## Utilisation

Dans **Mes sources → Découvrir une source**, indiquer une URL publique ou un nom.
Un nom nécessite un moteur de recherche configuré ; si plusieurs domaines sont
trouvés, choisir le bon site. Deux recherches de contrôle sont modifiables dans
les options du formulaire. Durée : 5 minutes par défaut, réglable de 1 à 60 minutes.

La tâche continue lorsque la fenêtre est fermée. Les découvertes récentes permettent
de retrouver son état, ses étapes, sa configuration et ses preuves. Le bouton Arrêter
annule les workers actifs. Une découverte active par compte et deux par serveur.
Un redémarrage interrompt les tâches : elles ne sont pas relancées silencieusement.

Les nouvelles sources sont enregistrées automatiquement après les contrôles. Une
configuration identique ne crée pas de doublon. Depuis l'éditeur d'une source,
**Analyser cette source** produit une proposition comparée à l'ancienne configuration.
Son application est explicite et sauvegarde la configuration précédente dans
`source_assistant_backups`. Si la source a été modifiée entre-temps, l'application
est refusée : relancer l'analyse.

## Configuration administrateur

Accès depuis **Mon compte → Découverte des sources**, ou depuis l'assistant.
Les services sont partagés, tandis que les tâches, sources et propositions sont privées.

### Recherche web

- SearXNG : URL de base, par exemple `http://searxng:8080`. L'assistant appelle
  `/search?q=...&format=json`. Le format JSON doit être activé dans SearXNG.
- HTTP JSON adaptable : URL exacte de l'endpoint, GET ou POST JSON, nom du paramètre
  de recherche et chemins JSON Pointer de la liste et de chaque champ.
- En-têtes secrets : objet JSON, par exemple `{"X-API-Key":"..."}`. Ils sont chiffrés.
- **Enregistrer et tester** présente les résultats normalisés. Le nom d'un produit
  tel que « degoog » ne suffit pas à confirmer son protocole : utiliser ce test.

### IA

- Ollama : URL de base telle que `http://192.168.0.10:11434`, modèle installé.
- API compatible OpenAI : URL de base **incluant `/v1`** lorsque le fournisseur
  l'exige, modèle et jeton Bearer. L'API doit accepter `/chat/completions` et
  `response_format: {"type":"json_object"}`.
- Le fournisseur sélectionné est le seul utilisé. Aucun basculement payant,
  téléchargement de modèle ou plafond financier n'est géré par AnyTube.
- Le mode Sans IA conserve reconnaissance, formulaires HTTP et inférence JSON/HTML.

Les secrets réutilisent AES-GCM et la clé externe `ANYTUBE_VAULT_KEY_FILE` du coffre.
Le namespace des services est réservé et ne correspond à aucun compte utilisateur.
Laisser un secret vide conserve sa valeur ; la case d'effacement le supprime.
Les endpoints privés sont autorisés uniquement pour ces services administrateur.
Les pages découvertes, redirections et résolutions DNS restent publiques uniquement.

### Navigateur optionnel et Unraid

Le navigateur est un service distinct, sans volumes personnels ni port publié par
défaut. Il utilise un jeton Bearer partagé avec AnyTube.

```sh
# Définir ANYTUBE_BROWSER_TOKEN dans le fichier .env non versionné.
docker compose -f compose.yaml -f compose.browser.yaml --profile discovery build
docker compose -f compose.yaml -f compose.browser.yaml --profile discovery up -d
```

Dans AnyTube : URL `http://source-browser:8010`, jeton identique à la variable.
Sur Unraid, connecter les deux conteneurs au même réseau Docker utilisateur et
utiliser le nom du conteneur. Pour un moteur sur le PC, utiliser son adresse LAN,
pas `localhost` qui désigne le conteneur. Ne pas exposer ce navigateur à Internet.
La clé du coffre doit aussi être montée en lecture seule dans le conteneur AnyTube,
comme pour les accès aux sources existants.

Chromium s'exécute sous un utilisateur non root, sandbox activée. Le noyau et le
profil Docker doivent permettre ses espaces de noms utilisateur. Si ce prérequis
n'est pas satisfait, l'observation échoue et la découverte HTTP reste disponible ;
ne pas désactiver la sandbox pour contourner cet échec. Le service navigateur
nécessite une vérification sur l'hôte Docker cible avant utilisation.

Toutes les requêtes HTTP du navigateur sont interceptées puis servies par des
workers avec contrôle DNS public. Son accès direct utilise un proxy local fermé,
les WebSockets sont fermés, les service workers bloqués, aucun cookie importé.
Les sessions sont détruites après l'observation et les échantillons ne sont pas
conservés. Observation plafonnée à 85 secondes et 80 requêtes, réponses à 2 Mo.

Référence technique : [interception Playwright](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-route).

## Ce qui est réellement automatisé

1. Réutilisation d'un modèle dont un domaine correspond exactement au site.
2. Reconnaissance d'une instance PeerTube via son endpoint public de configuration.
3. Lecture HTML, formulaires de recherche GET, liens API/documentation/scripts,
   recherche documentaire via le moteur choisi.
4. Observation optionnelle d’un champ de recherche, de ses réponses JSON GET et du HTML rendu.
5. Inférence de connecteurs JSON/HTML et propositions IA strictement déclaratives.
6. Deux recherches distinctes, témoin aléatoire, contrôle des titres/URL et pagination.

Un connecteur inféré sans preuve de pagination reçoit le mode **Première page
uniquement** : aucun bouton de suite ne doit annoncer une pagination non vérifiée.
Les pages natives répétées sont refusées. Les extracteurs sont identifiés par leurs
motifs d'URL lorsque le rapprochement est unique ; cela ne prouve pas la lecture.
L'IA n'a aucun outil de terminal, édition du dépôt ou exécution de code.

Limites : formulaires complexes, POST JavaScript, réponses nécessitant des cookies,
CAPTCHA, DRM et connecteurs non exprimables dans le schéma existant ne sont pas
automatiquement résolus. Deux corrections IA au total ; au plus trois nouveaux
candidats, six endpoints inférés et trente lectures HTTP de découverte. Les tailles,
la durée globale et les limites des workers s'appliquent aussi.

Une recherche réussie ne certifie ni une plateforme entière, ni l'extraction,
les collections, la vidéo, l'audio, le direct, les sous-titres ou les téléchargements.
L'assistant n'édite pas les modèles distribués et ne déploie aucune modification.

## API et données

- `GET/PUT /api/source-assistant/settings`, administrateur uniquement.
- `POST /api/source-assistant/settings/test/{search|ai|browser}`.
- `GET/POST /api/source-assistant/jobs`, `GET /jobs/{id}`.
- `POST /jobs/{id}/cancel`, `/choose` avec une URL proposée, `/apply` pour une mise à jour.
- SQLite : `source_assistant_jobs`, `source_assistant_backups` ; migration additive.
- Les tâches terminées et leurs preuves expirent après 30 jours. Les sauvegardes
  de configurations restent disponibles. La maintenance passe chaque minute.
- Les preuves incluent la révision du moteur ; une modification du moteur peut
  rendre historiques les contrôles existants, selon la politique AnyTube actuelle.

## Vérification de cette livraison

Les tests déterministes couvrent API, secrets, isolation, reprise, doublons,
inférence et contrats des services simulés. Les trois branches du pipeline
(PeerTube, formulaire/API, observation navigateur) sont exercées avec réponses simulées.
La suite complète passe : 173 tests, dont 27 consacrés à cet assistant.
Les contrôles de syntaxe JavaScript, `git diff --check` et la résolution Compose passent.

Un essai réel depuis l'interface sur framatube.org a ajouté la source en **5,960 s**,
sans édition de connecteur ni appel IA. Le bilan est dans
`source-assistant-live-check.json`. Cela mesure une réutilisation de modèle, pas
la découverte d'une API inconnue. Fermeture/réouverture du bilan vérifiée.
Une relance contrôlée s'est terminée en 7,392 s sans doublon ; une annulation en
0,598 s. La source a ensuite été utilisée dans la recherche normale de l'application.

La version 0.4.0-preview a été construite sur Unraid et les 173 tests passent
dans son image Python 3.14 (avec les dépendances de test). Le moteur de recherche
de test utilise le relais degoog-compat local, qui renvoie dix résultats normalisés.
Chromium reste optionnel et non activé dans ce déploiement ; son protocole est testé
avec un service simulé. Aucune couverture de sites JavaScript réels n'est annoncée.

## Réseau du conteneur Unraid

Les découvertes publiques utilisent le proxy filtrant existant. Les services
configurés par l’administrateur utilisent un second proxy interne authentifié,
avec un identifiant éphémère renouvelé à chaque démarrage et retiré de
l’environnement des processus d’extraction. Aucun port supplémentaire n’est publié.
Les redirections de ces services sont refusées et les identifiants du proxy
ne sont pas transmis aux services cibles.

Recette Docker sur le réseau Compose Unraid : Framatube ajoutée en 10,226 s,
quatre contrôles de recherche, aucun appel IA. Une URL privée fournie comme
cible de découverte est refusée. La base de recette est jetable et séparée.
## Browserless v2 (0.4.1-preview)

Le champ navigateur attend la passerelle AnyTube, pas directement Browserless.
Browserless expose un protocole CDP WebSocket ; il ne fournit pas les routes
`/health` et `/observe` de l'assistant. La passerelle peut maintenant l'utiliser :

```dotenv
ANYTUBE_INSTALL_CHROMIUM=false
ANYTUBE_BROWSER_CDP_URL=ws://browserless-v2:3000/chromium
ANYTUBE_BROWSER_CDP_TOKEN=jeton-browserless
ANYTUBE_BROWSER_TOKEN=jeton-prive-de-la-passerelle
```

Ces variables appartiennent au service `source-browser`. Dans l'interface AnyTube,
conserver `http://source-browser:8010` et le jeton privé de la passerelle. Les deux
services doivent être joignables sur leur réseau Docker. Le jeton Browserless reste
côté serveur. Le test vérifie une connexion et la création d'un contexte isolé.
Les délais incluent le démarrage à froid ; l'échéance globale reste prioritaire.

Recette sur Unraid : Browserless a exécuté un formulaire JavaScript de test et la
passerelle a capturé son appel JSON (deux requêtes, une réponse JSON). Le test utilise
une page contrôlée et des réponses HTTP simulées, avec le vrai Chromium distant.
La page publique Allociné a également été chargée ; la détection d'une recherche
compatible sur ce site n'est pas validée. Un champ de localisation de salles est
exclu de la sélection automatique de recherche générale.

Une observation connectée sans API JSON exploitable ne rend pas le site compatible.
Depuis 0.5.0, le HTML reproductible par URL GET est pris en charge sous les contrôles décrits plus haut ; la couverture reste partielle.
Les bilans distinguent désormais connexion navigateur, absence de JSON, absence de
candidat IA et contrôles de recherche échoués.
