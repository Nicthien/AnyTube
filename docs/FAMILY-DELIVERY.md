# Livraison familiale — état vérifiable au 6 septembre 2026

La demande complète n’est **pas terminée**. Cette version livre le socle familial et une première validation Docker ; elle ne certifie pas les 1 750 extracteurs.

## Implémenté

- Comptes sur invitation, premier administrateur par jeton unique, Argon2id, sessions serveur, déconnexion/révocation/changement de mot de passe, limitation des tentatives et contrôle des mutations.
- Sources, préférences, favoris, historique, reprise, tâches et accès aux fichiers privés par compte ; migration des anciennes sources vers le premier administrateur.
- Bibliothèque persistante distincte du cache, quotas administrables, progression, annulation, nouvelle tentative, détection des interruptions et entretien du cache.
- Recherche et accueil avec curseurs liés au compte et aux filtres, chargement supplémentaire, déduplication et erreurs partielles ; dix vidéos par source au premier chargement de l’accueil.
- Modèles livrés distincts des configurations personnelles, comparaison avant application, copie et restauration dans un brouillon. Essais conservés avec configuration, version de connecteur et version yt-dlp ; changements invalidant les anciens résultats.
- Rapport exportable : inventaire automatique de 1 750 extracteurs regroupés en 927 familles de modules. Le rapport identifie son statut d’inventaire, distinct d’un examen complet des plateformes.
- Déploiement en un conteneur : serveur web, proxy local contrôlant et fixant les adresses DNS publiques, sauvegardes quotidiennes et pare-feu par UID. Les droits limités au démarrage et ceux du superviseur sont détaillés dans UNRAID.md.

## Validé localement

- 35 tests automatiques passent : comptes, isolation, sessions révoquées, invitations utilisées/expirées, accès direct/Range aux fichiers, quotas, reprise des tâches, curseurs et erreurs partielles, invalidation des vérifications, DNS privés/IPv6 et sauvegarde SQLite avec archive des configurations.
- Image construite et pile démarrée sur volumes vides. Migration de la base historique sauvegardée ; intégrité de cette sauvegarde `ok`.
- Recherche réelle « chat » sur Dailymotion dans le réseau Docker isolé : dix résultats, aucune erreur. Interface filtrée Dailymotion : huit puis seize cartes avec Charger davantage.
- Appels publics HTTPS autorisés ; accès au LAN directement impossible, accès au LAN et à 169.254.169.254 via le proxy refusé avec HTTP 403.
- Big Buck Bunny, URL officielle Blender sur YouTube `aqz-KE-bpKQ` : préparation MP4, 161 192 091 octets, Range HTTP 206, conservation après redémarrage du conteneur, téléchargement à nouveau accessible.
- Lecture navigateur : readyState 4, durée 634,62 s, temps de lecture observé à 37,02 s.
- Sauvegarde cohérente après redémarrage : intégrité `ok`, tâche média conservée.
- Interface examinée à 390×844 et 1280×900, thèmes clair/sombre, compte, accueil, recherche filtrée et lecture ; absence de dialogues JavaScript natifs contrôlée par tests.

## Limites et développements ouverts

- L’examen des API et fonctions de **toutes** les plateformes n’est pas fait. Les 927 familles sont un regroupement technique, pas une liste validée de plateformes distinctes. Les anciens essais de 28 modèles sont historiques ; ils ne prouvent pas la compatibilité actuelle de lecture/téléchargement.
- Développer les adaptateurs publics manquants par lots documentés, puis exécuter plusieurs recherches et des tests média appropriés pour chaque connecteur annoncé vérifié. Distinguer authentification requise et indisponibilité lorsque le moteur peut fournir une preuve fiable.
- La pagination recharge un préfixe croissant de résultats, avec un plafond de 100 par source. Des pages natives/cursors propres aux API restent à développer ; les classements changeants peuvent modifier les positions entre requêtes.
- Les filtres durée/date ne sont actuellement proposés que pour Dailymotion. Les préférences synchronisées couvrent thème, SponsorBlock, sources et classement d’accueil ; les filtres de recherche ne sont pas encore tous persistés.
- Les tests réseau couvrent les adresses privées et DNS épinglé ; compléter par une matrice intégrée de redirections et rebinding pour tous les transports média.
- Journalisation à durcir pour garantir le masquage de tous les paramètres sensibles éventuellement renvoyés dans les erreurs des plateformes.
- Pas de HLS adaptatif, direct, choix de qualité ou sous-titres : préparation MP4 jusqu’à 720p/500 Mo uniquement.
- Recette réelle Unraid, création du premier administrateur par l’utilisateur, proxy HTTPS, Wi-Fi/extérieur, exercice complet de restauration et retour d’image : suivre l’état du déploiement, sans les déduire de la validation locale.

## Déploiement réel Unraid

- Un seul conteneur AnyTube regroupe le serveur web, le proxy sortant local et la sauvegarde ; service sain. Démarrage automatique activé dans Compose Manager. Adresse LAN contrôlée : `http://192.168.0.5:18088`.
- Migration : deux sources historiques, intégrité SQLite `ok`, premier administrateur à créer. Les anciens paramètres sont sauvegardés sous `backups/before-family-local.db` ; la migration garde aussi `data/before-family.db`.
- Test exécuté dans le conteneur réel : dix résultats Dailymotion pour « chat » et dix pour « nature », IP privées et métadonnées refusées par le proxy (403), connexion directe au LAN bloquée.
- Écran de création du premier administrateur affiché dans Chrome depuis le serveur. Aucun compte familial fictif n’a été créé sur cette installation.
- HTTPS configuré le 6 septembre 2026 : route Zoraxy `anytube.vnmaison.site` vers `192.168.0.5:18088`, certificat dédié demandé via Let's Encrypt. Contrôle TLS sans contournement réussi et écran d’installation affiché sur `https://anytube.vnmaison.site/`. `ANYTUBE_PUBLIC_URL` configuré et service applicatif recréé ; premier compte toujours à créer par l’utilisateur. Les autres routes n’ont pas été modifiées. La recette depuis un réseau extérieur reste à effectuer.

## Regroupement en un conteneur — validation locale

- Image construite et démarrée sur volumes vides : service sain.
- Migration des volumes de validation précédents : compte conservé, intégrité SQLite `ok`, vidéo MP4 de 161 192 091 octets conservée et Range HTTP 206 (100 octets) après redémarrage.
- Nouvelle préparation réelle de Big Buck Bunny via YouTube avec le nouveau pare-feu : terminée, 161 192 091 octets, sans erreur.
- Sous UID applicatif : accès directs au LAN, métadonnées, Internet et API locale bloqués ; le proxy refuse LAN/IPv6 privée/métadonnées (403). HTTPS public autorisé (200), recherche Dailymotion « chat » : dix résultats. Capacités effectives et limites de capacités nulles, no-new-privileges actif.
- Arrêt volontaire du proxy dans le conteneur de validation : superviseur arrêté, redémarrage Docker automatique, retour à l’état sain.
- Une sauvegarde SQLite cohérente est produite par le processus intégré. Aucun conteneur de sauvegarde séparé n’est nécessaire.

## Regroupement installé sur Unraid

Le 6 septembre 2026, la migration vers `/mnt/user/appdata/anytube/releases/single-preview` a réussi. Un seul conteneur du projet reste présent : `anytube-anytube-1`, sain. Les conteneurs gateway/egress/backup et les trois anciens réseaux ont été supprimés. Le projet Compose Manager et son démarrage automatique sont conservés.

Sauvegardes cohérentes avant et après : `anytube-20260906T151111Z.db` et `anytube-20260906T151151Z.db`. Base actuelle intègre, deux sources historiques conservées, aucun compte administrateur encore créé. Les volumes restent aux mêmes emplacements. L’ancienne image `anytube:family-multi-previous` et `deploy/before-single-compose.yml` sont gardés pour le retour arrière.

Les contrôles exécutés dans le conteneur Unraid ont confirmé les mêmes blocages réseau et dix résultats Dailymotion ; voir `single-container-verification.json`. L’API publique répond en HTTPS avec certificat validé. Les nouveaux essais de préparation média, reprise après redémarrage et panne de sous-processus ont été faits sur Docker local ; aucune lecture familiale authentifiée sur Unraid n’est revendiquée. Le conteneur temporaire de validation local et son réseau ont été supprimés après les essais.

## Connexion par adresse locale

Correction déployée le 6 septembre 2026 après création du compte administrateur : redirection HTTP locale vers le domaine HTTPS configuré, contrôle de santé local préservé. Test de connexion avec cookie Secure et de terminaison TLS derrière proxy ajouté : 36 tests passent. Aucun mot de passe utilisateur réinitialisé.
