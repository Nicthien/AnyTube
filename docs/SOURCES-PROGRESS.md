# Extension des sources — état du 6 septembre 2026

Le plan exhaustif reste **en cours**. Ce lot fournit un socle et des parcours génériques ; il ne certifie pas la compatibilité de toutes les plateformes.

## Livré dans le code

- Inventaire recalculé de 1 750 extracteurs, 927 familles inférées et 31 modèles de recherche. Les associations et rôles inférés ne sont pas des revues humaines. Le répartiteur `Generic` de yt-dlp n'est pas une plateforme et n'est pas inclus dans ces totaux.
- Matrice par fonction, références au code yt-dlp installé, révisions et historique des preuves privées par compte. Les changements du moteur ou des identifiants rendent les preuves précédentes obsolètes.
- Adaptateurs compatibles avec les anciennes configurations ; JSON GET/POST ; pagination par page/décalage pour les API compatibles ; rechargement de préfixe explicitement limité pour les autres.
- Coffre AES-GCM par compte pour clés API, bearer et cookies importés, références séparées pour la recherche et le média, domaines explicitement autorisés, révocation et rotation. Aucun OAuth ni formulaire utilisateur/mot de passe par plateforme n'est encore implémenté.
- Résolution média, relais privé de manifestes et segments, sessions expirables, Shaka 5.2.9 servi localement, choix des qualités/pistes, navigation de collections et file de lecture.
- Téléchargement VOD segmenté sans DRM, fusion locale H.264/AAC, extraction audio M4A, limites administrables et contrôle ffprobe du fichier final. Les fragments manquants font échouer la préparation.
- Modales intégrées pour les accès et les sources ; aucun dialogue JavaScript natif.

## Preuves et limites

`source-audit-current/` contient 74 essais réseau sur les 16 familles possédant les modèles concernés : 33 réponses avec résultats, 14 réponses vides, 22 échecs temporaires et 5 accès nécessitant une authentification. Chaque scénario conserve les comptes de résultats et de nouvelles URL de ses deux pages. Une réponse avec résultats ne valide pas automatiquement la pagination, la pertinence, la lecture ou la plateforme entière. L'audit porte la révision `159bd06af220c5ff` ; les changements média ultérieurs rendent cette preuve historique et imposent une nouvelle recette avant toute certification de la révision finale.

`source-audit/` est un premier passage historique : certains essais PeerTube/Vimeo utilisaient un processus enfant provenant d'une autre version du code. Ne pas utiliser ces essais comme preuve de compatibilité. Le répertoire `source-audit-current/` a été exécuté après correction du répertoire de travail du processus enfant.

Docker local, port 18089, compte de recette dédié : recherches Dailymotion sur deux pages distinctes ; résolution YouTube ; téléchargement de Big Buck Bunny (chaîne Blender, `aqz-KE-bpKQ`) en vidéo H.264/AAC et audio AAC ; réponses Range 206 ; conservation après recréation du conteneur. ffprobe : vidéo 634,625 s, audio 634,586 s. Les résultats API sont dans `sources-docker-validation.json`.

Chrome : lecture HLS réelle du même film, tampon audio et vidéo présents, `readyState=4`, progression de 0 à 22,975817 s et 699 images décodées, puis déplacement avec la commande clavier du lecteur. Cette recette a identifié et corrigé les segments AAC annoncés `application/octet-stream`. Image testée : `sha256:9b88b510eb9fc5a99756140fd0fd08c5f3341f14afdd5fcbb63a8c864c2b967f`. La construction suivante ajoute le contrôle ffprobe en fin de préparation ; cette nouvelle garde n'a pas encore sa recette réseau complète.

Les modales d'accès ont été inspectées à 390 px dans les deux thèmes et sur ordinateur. Firefox, Safari, lecture authentifiée auprès d'une plateforme, DASH réel, changement de langues/sous-titres et direct restent non vérifiés. Le compte AnyTube de test est authentifié ; cela ne constitue pas une preuve d'authentification auprès d'une plateforme externe.

50 tests déterministes passent dans `.venv`, dont le garde-fou des dialogues natifs, et `git diff --check` passe. Le dépôt étant encore non suivi, ce dernier ne couvre pas les fichiers nouveaux. Le Python global Windows n'a pas yt-dlp ; utiliser l'environnement du projet avec `requirements-dev.txt` pour les tests. L'image de production ne contient pas le client HTTP de test.

## Travail restant

1. Registre de revues éditable/versionné : examiner les 927 regroupements et les interfaces officielles plateforme par plateforme ; relier les preuves à une identité de source stable à travers les modifications de configuration ; consolider les totaux vérifiés depuis les preuves.
2. Corriger les modèles en erreur ; ne pas transformer un résultat vide ou une panne temporaire en impossibilité. Implémenter et auditer les autres familles par lots de vingt maximum.
3. Authentification spécifique par plateforme, OAuth, curseurs natifs opaques et filtres supplémentaires ; comptes fournis uniquement via le coffre.
4. Cas DASH avec héritage complexe de BaseURL, segments supérieurs à 8 Mio, plages suffixes, reprises réseau du direct, enregistrement borné du direct, conversion de tous les formats annoncés compatibles, sélection multiple de téléchargements et file persistante.
5. Tests navigateur complets, tests média par capacité et plateforme, sauvegarde/restauration de l'ensemble du lot sur installation vierge puis migrée, déploiement et recette Unraid.

La production Unraid n'a pas été mise à jour par ce lot. L'accès SMB fonctionne, mais le terminal navigateur n'a pas fourni de preuve d'exécution du diagnostic et les captures Chrome ont expiré. Aucun changement de l'extension ou réduction des protections du navigateur n'a été effectué. La recette locale utilise une session créée par l'API du compte de test, évitant les saisies de mot de passe et les fenêtres de gestionnaire de mots de passe.
