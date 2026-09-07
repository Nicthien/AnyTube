# 0.5.0-preview — exemples et recherche HTML

## Changements

- Exemples vidéo et URL de recherche facultatifs dans la découverte.
- Recherche HTML déclarative HTTP ou Chromium, intégrée à la recherche habituelle.
- Titres, liens relatifs, miniatures, durées et pagination ; contrôle des pages vidéo.
- Reprise privée avec exemples préremplis, historique et protection contre les doublons.
- Aucun script généré, aucune validation implicite de lecture ou d’extraction.

## Recette avant publication (8 septembre 2026)

193 tests Python ont passé sur Windows et dans l’image Docker candidate. Les
contrôles de syntaxe JavaScript, de diff et d’absence de dialogues natifs passent.
Les tests couvrent JSON, HTML, erreurs IA, absence du navigateur, délais, arrêt,
reprise, pagination, URL privées, secrets et séparation des propriétaires.

Le scénario HTML simulé passe par la création de tâche, l’ajout de source et
`/api/search`, puis sa seconde page. La reprise conserve l’identifiant de source.

Dans Docker, une vraie session Browserless/Chromium exécute le JavaScript d’un
site simulé sans API JSON de recherche. Découverte, ajout puis recherche normale
réussis en **15,166 s**, sans édition de connecteur ni appel IA. Ce chiffre inclut
le parcours du script, pas une comparaison avec un ancien temps de configuration.

Sur le site public TED, une base temporaire a reçu deux exemples de conférences
et `https://www.ted.com/search?q=science` avec le terme `science`. Le connecteur
HTML a été inféré sans modèle de recherche préexistant ni appel IA : **38,799 s**,
**18 appels HTTP**, quatre contrôles de recherche, pagination vérifiée. Les pages
vidéo contrôlées exposent leurs métadonnées. La lecture n’a pas été testée.

L’essai public Canal-U a retourné HTTP 403 ; aucune compatibilité n’est annoncée.
Les mesures dépendent du site, du réseau et du démarrage du navigateur.

## Déploiement

Conserver la passerelle AnyTube et les paramètres Browserless existants. Le
nouveau navigateur doit être livré avec le backend : il fournit désormais le HTML
rendu en plus des observations JSON. Les anciens connecteurs restent lisibles.
Les preuves deviennent obsolètes lorsque la révision du moteur change.

Sauvegarder base, images et configuration Compose avant changement. Vérifier le
SHA-256 de l’archive, puis santé, version, fichiers servis et recherche réelle après
déploiement. En cas de régression bloquante, restaurer les images et Compose
précédents. Aucun secret ni profil navigateur ne fait partie de cette release.
