# Validation locale — 6 septembre 2026

- Huit tests Python réussis : sources persistantes, doublons, suppression, sélection de recherche, résultats partiels, URL refusées, IP privées, réponses Range, métadonnées non fiables, CSP et SponsorBlock.
- Syntaxe JavaScript et configuration Docker Compose validées.
- Navigateur réel : recherche « Big Buck Bunny », huit résultats YouTube avec vignettes et descriptions. Dailymotion a renvoyé zéro résultat pour cette recherche ; aucun engagement de disponibilité n’est déduit de ce test.
- Ajout de Vimeo depuis le catalogue, source conservée après redémarrage, puis suppression via la modale intégrée.
- Affichage contrôlé à 390 × 844 et sur bureau, thèmes clair et sombre.
- Vidéo de test : `https://www.youtube.com/watch?v=aqz-KE-bpKQ` (Blender, Big Buck Bunny). Téléchargement puis fusion réussis, MP4 de 161 192 142 octets. Lecture navigateur constatée avec `readyState=4`, durée de 634,62 secondes et temps de lecture avançant au-delà de 39 secondes.
- API SponsorBlock réelle joignable ; aucun segment pour cette vidéo. Le saut effectif d’un segment signalé n’a pas été vérifié en lecture réelle.
- Image Docker non construite localement : moteur Docker Desktop arrêté. Aucun déploiement serveur effectué.

Les dépendances et les formats proposés par les plateformes évoluent : ces observations ne garantissent pas la compatibilité de toutes les vidéos.

## Correction de la recherche Dailymotion

- Reproduction sur le service local : `chat` avec Dailymotion seule donnait zéro résultat et aucune erreur via le connecteur yt-dlp.
- L’API de catalogue Dailymotion renvoyait des vidéos pour la même requête. La recherche utilise désormais cette API ; aucun téléchargement vidéo n’est nécessaire pour construire les cartes.
- Après correction, la même requête sur `/api/search` renvoie huit vidéos Dailymotion sans erreur, dont « Chats chats chats » et « chat VS. chat ».
- Trois tests de régression supplémentaires : métadonnées et encodage de la requête, distinction entre réponse vide et invalide, propagation des erreurs HTTP. Onze tests réussis au total.

## Connecteurs éditables et sources manuelles

- Migration SQLite des sources existantes, sans perte de noms ni d’état activé/désactivé.
- Éditeur Dailymotion ouvert dans le navigateur : URL, chemin de résultats et champs préremplis. « Tester sans enregistrer » renvoie trois résultats réels pour `chat` et affiche leur JSON normalisé.
- Création d’une source indépendante par copie, modification de son nom et suppression du mapping de description depuis l’interface. Recherche réelle sur cette source : huit résultats, toutes les descriptions vides conformément au réglage. La source temporaire a ensuite été retirée.
- Quinze tests réussis : migration, création/modification/persistance, recherche sur une source personnalisée, test sans sauvegarde, mapping imbriqué et clés échappées, validation des modèles, réponses surdimensionnées et redirections privées.

## Vidéos par source sur l’accueil

- API et navigateur réels : dix vidéos récentes Dailymotion et dix résultats YouTube de la recherche configurée `vidéos`, chargés automatiquement et regroupés par source.
- Trois tests supplémentaires couvrent la limite de dix, le cache et sa variation avec la configuration, les sources absentes/désactivées/URL uniquement, les erreurs réessayables et le choix de l’URL de flux JSON. Dix-huit tests réussis.
