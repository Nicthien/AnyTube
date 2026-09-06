# Exploitation Unraid — version familiale

## Coffre des accès aux sources

Le nouveau lot de sources nécessite `ANYTUBE_VAULT_KEY_FILE=/secrets/vault.key` et un volume distinct `ANYTUBE_SECRETS` (par défaut `/mnt/user/appdata/anytube-secrets`). Le superviseur crée une clé aléatoire uniquement au premier démarrage sans identifiants chiffrés existants ; si la base contient des identifiants et que la clé manque, le démarrage échoue. Ne jamais remplacer une clé manquante par une nouvelle.

La clé n'est pas incluse dans les sauvegardes ordinaires de la base/configuration. Conserver une copie privée séparée de cette clé, avec sa propre politique de restauration. Restaurer ensemble la base et la clé correspondante avant de relancer l'image ; les références d'accès dans SQLite ne permettent pas de récupérer une clé perdue. Préserver l'image précédente et la sauvegarde SQLite pré-migration avant toute mise en service du lot. L'état précis de ce lot et des recettes restantes est dans `SOURCES-PROGRESS.md`.

## Répertoires

- Code et image : `/mnt/user/appdata/anytube/releases/single-preview`.
- SQLite, comptes et configurations : `/mnt/user/appdata/anytube/data`.
- Sauvegardes : `/mnt/user/appdata/anytube/backups`.
- Cache et bibliothèques : `/mnt/user/anytube`, dans des sous-répertoires séparés.
- Pile Compose Manager : `/boot/config/plugins/compose.manager/projects/anytube`.

`ANYTUBE_APPDATA`, `ANYTUBE_STORAGE`, `ANYTUBE_BIND`, `ANYTUBE_PORT` et `ANYTUBE_PUBLIC_URL` se configurent dans `.env`. Ne jamais partager ce dossier en accès public : SQLite contient les hachages des mots de passe, sessions et invitations. Les jetons d’installation figurent uniquement dans les journaux et expirent après leur utilisation ou sont renouvelés au redémarrage tant qu’aucun administrateur n’existe.

## Premier démarrage et réseau

Construire l’image, puis lancer la pile depuis son répertoire :

```sh
docker compose build anytube
docker compose up -d
docker compose ps
docker compose logs --tail 30 anytube
```

Un seul conteneur `anytube` contient le serveur web, le proxy sortant local et les sauvegardes quotidiennes. Zoraxy reste le proxy HTTPS existant du NAS. Le port 18088 pointe directement vers le serveur web du conteneur.

Au démarrage, un programme prépare les droits des volumes et installe un pare-feu dans le réseau propre au conteneur avec les capacités limitées déclarées dans Compose (notamment NET_ADMIN). Aucun mode privilégié, réseau hôte ou socket Docker n’est utilisé. Ensuite, l’application et FFmpeg tournent sous UID 10001, le proxy sous UID 10002, sans capacités et avec no-new-privileges. Le superviseur ne garde que CAP_KILL pour arrêter ses enfants. Toute défaillance d’un service arrête le conteneur ; Docker le relance.

Le pare-feu permet à l’application de joindre uniquement le proxy local. Ce proxy valide les DNS publics, fixe l’adresse de connexion et refuse les réseaux privés ; le pare-feu les bloque également. Les connexions sortantes IPv6 sont désactivées. Le contrôle de santé utilise un UID distinct autorisé à consulter le serveur local. Si le pare-feu ne peut pas être installé, le démarrage échoue ; ne pas contourner cette erreur en supprimant la protection. Les noyaux Docker/Unraid doivent prendre en charge iptables et le filtrage par propriétaire.

Ouvrir l’URL LAN, choisir le nom et le mot de passe du premier administrateur, saisir le jeton des journaux. Les anciennes sources sont attribuées à cet administrateur. Les comptes invités commencent avec leurs propres sources vides. Les invitations se créent dans Mon compte et sont à usage unique pendant sept jours.

Après validation LAN, configurer le proxy existant pour `anytube.vnmaison.site` vers `http://192.168.0.5:18088`, certificat HTTPS valide, sans publication Internet directe de 18088. Renseigner ensuite `ANYTUBE_PUBLIC_URL=https://anytube.vnmaison.site` et recréer le service applicatif. Les cookies deviennent Secure : la connexion devra alors passer par HTTPS, y compris depuis le téléphone sur le Wi-Fi. Lorsque cette adresse HTTPS est configurée, les accès par une autre adresse (notamment l’IP locale) sont redirigés vers elle. Les anciennes tentatives de connexion HTTP sont refusées avec une indication de l’adresse HTTPS, afin d’éviter une session perdue à cause des cookies Secure. Le contrôle de santé local reste accessible.

## Sauvegarde quotidienne

Le processus de sauvegarde intégré utilise l’API SQLite Backup, vérifie l’intégrité et conserve sept sauvegardes. Les sources, comptes, préférences, tâches et réglages sont inclus dans SQLite. Chaque sauvegarde comporte aussi une archive `.config.zip` avec `.env`, Compose, les fichiers de déploiement et le verrou des dépendances. Les fichiers média restent dans `/mnt/user/anytube` et doivent faire partie de la stratégie de sauvegarde du NAS si leur récupération après panne disque est nécessaire. Conserver également l’image et le code correspondant à chaque version déployée.

Sauvegarde immédiate avant mise à jour :

```sh
docker compose exec -u 10001:10001 anytube python -m app.backups
```

## Restauration sans effacement

Arrêter l’application et la sauvegarde avant toute restauration. Choisir une sauvegarde compatible avec l’image. Copier le dossier `data` actuel vers un nouveau dossier horodaté, conserver aussi l’image actuelle et son fichier Compose. Ne pas mélanger une ancienne base et une bibliothèque dont les fichiers ont été supprimés depuis cette sauvegarde.

```sh
docker compose stop anytube
```

Vérifier `PRAGMA integrity_check` sur une copie de la sauvegarde. Renommer `data` en `data-before-restore-<date>`, recréer `data`, y copier **uniquement** la sauvegarde SQLite choisie sous le nom `anytube.db` (sans réutiliser d’anciens fichiers WAL/SHM), puis attribuer les droits 10001:10001. Les volumes vidéo restent en place. Relancer la pile, vérifier l’état, se connecter et tester un fichier conservé. En cas d’échec, arrêter les services et remettre le dossier sauvegardé et l’image précédente.

La migration familiale crée automatiquement `before-family.db` avant changement du schéma historique. Cette copie est compatible avec l’ancienne application ; une base familiale ne l’est pas nécessairement. Le test automatisé de restauration valide l’intégrité et la conservation des données ; l’exercice complet de retour à une image précédente sur Unraid reste à effectuer.

## Diagnostics et mises à jour

`/api/health` expose l’état et les versions sans données privées. Mon compte affiche l’espace disponible et les tâches en erreur pour l’administrateur ; `/api/admin/diagnostics` complète ce diagnostic. Mes sources exporte le rapport de catalogue avec les essais actuels privés du compte.

Une mise à jour yt-dlp passe par une modification du verrou de dépendances, les tests, des essais réels des fonctions annoncées et une reconstruction d’image. Aucun téléchargement automatique d’une nouvelle version de yt-dlp à l’exécution. Conserver l’image précédente avant remplacement et sa sauvegarde SQLite compatible.

## Recette à terminer sur l’installation réelle

Compte administrateur choisi par l’utilisateur ; compte invité distinct ; recherche, lecture et conservation d’un média ; téléchargement sur téléphone ; redémarrage et relecture ; vérification depuis le Wi-Fi puis un réseau extérieur ; restauration et retour à l’image précédente. La recette locale Docker est consignée séparément dans `FAMILY-DELIVERY.md`.
