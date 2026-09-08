# Découverte traçable — validation locale

Ce changement est inclus dans la préversion 0.5.3. Le bilan ci-dessous décrit la validation locale préalable à la publication. Il concerne le mécanisme général ; aucune compatibilité avec un site public supplémentaire n’est annoncée.

## Comportement

Les endpoints portent une provenance : modèle, exemple utilisateur, formulaire GET, documentation, hypothèse IA ou observation navigateur. Les formulaires GET conservent leur action relative, le nom du champ de recherche et les paramètres fixes non secrets. Un formulaire POST est signalé, sans invention d’une URL GET.

Une hypothèse est interrogée directement. Lorsqu’une réponse correspond à l’accueil (contenu identique ou redirection), le deuxième terme est essayé avant de rejeter l’endpoint. Un HTTP 200 seul ne confirme rien. Les deux recherches et le témoin doivent ensuite satisfaire les contrôles existants.

Les résultats vides, résultats identiques, témoin répétitif, champs manquants, pagination répétée, erreurs réseau et preuves vidéo manquantes ont des diagnostics distincts. Un terme sans résultat reste non concluant ; aucun autre terme n’est inventé.

Trois candidats initiaux sont autorisés, avec une place réservée aux candidats issus du navigateur lorsqu’il est configuré. Deux corrections IA distinctes au maximum peuvent suivre un contrôle de recherche confirmé et un défaut déclaratif corrigeable. Une configuration déjà contrôlée est ignorée, y compris lorsqu’elle revient comme correction. Une erreur réseau, un endpoint non confirmé ou une preuve vidéo manquante ne déclenche pas de correction de sélecteurs.

La reprise conserve l’ancienne tâche, mais recharge les pages et refait les contrôles. Les deux termes peuvent être modifiés dans « Recherches de contrôle ». L’ajout automatique et la mise à jour explicite restent soumis à leurs contrôles ; la recherche ne valide pas la lecture ou l’extraction.

## Données et compatibilité

Les routes existantes restent identiques. Les réponses de tâches ajoutent `diagnostics_version`, `diagnostics` et `next_action`. La reprise accepte facultativement `queries`, toujours deux termes distincts soumis à la validation existante. Leur omission conserve les anciens termes.

Chaque événement peut contenir : date, identifiant du candidat, provenance, phase, état, code et message, terme, URL demandée/finale expurgées, statut HTTP connu, type de contenu, durée, résultats sélectionnés/valides et jusqu’à trois exemples titre/URL. Les informations inconnues ne sont pas transformées en succès ou en statut HTTP inventé.

Les événements sont enregistrés progressivement dans le JSON SQLite de la tâche. Les 400 événements les plus récents sont conservés ; chaque champ texte est borné à 2 000 caractères. Aucune page complète, capture réseau brute, cookie ou en-tête secret n’est ajouté aux diagnostics. La rétention de 30 jours et l’isolation par propriétaire existantes s’appliquent. Une ancienne tâche sans diagnostic reste consultable avec la mention correspondante.

La version de preuve inclut désormais le code de l’assistant et des diagnostics afin qu’une modification de validation invalide les anciennes preuves.

## Reproduction locale

Depuis la racine, avec l’environnement Python du projet :

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests
.venv/Scripts/python.exe scripts/check-source-diagnostics.py --browser
.venv/Scripts/python.exe scripts/check-source-diagnostics-ui.py
.venv/Scripts/python.exe scripts/check-html-browser.py
rg --files app/static -g '*.js' | ForEach-Object { node --check $_ }
git diff --check
```

Sans Playwright, omettre `--browser` pour les parcours HTML/JSON/échec. Les contrôles Chromium nécessitent l’installation locale facultative de `playwright==1.62.0` et de son Chromium. Les fixtures remplacent les requêtes aux sites par des réponses en mémoire ; elles ne sollicitent pas Unraid. Le test d’interface démarre temporairement AnyTube sur une adresse de boucle locale avec une base de test indépendante, puis arrête ce serveur.

Les tests couvrent notamment le refus de l’accueil déguisé en recherche, la distinction des erreurs, les doublons, le quota réservé au navigateur, la reprise, les diagnostics partiels, les secrets et l’isolation. Les captures UI sont écrites dans `.local/source-diagnostics-*.png`.

## Résultats observés

Validation locale : 219 tests Python réussis, contrôles JavaScript et absence de dialogues natifs vérifiés. Parcours UI HTML, JSON et Chromium réussis, ainsi qu’un échec explicite et une annulation. Fermeture/réouverture, navigation clavier, largeurs 1 400 et 390 pixels, thèmes clair/sombre vérifiés.

Mesures sur fixtures, comprenant la création puis une recherche normale pour les cas réussis :

| Parcours | Résultat | Durée indicative | Requêtes de pages | Observations Chromium | Éditions manuelles |
|---|---|---:|---:|---:|---:|
| HTML | Source ajoutée, recherche utilisable | 1,13 s | 13 | 0 | 0 |
| JSON | Source ajoutée, recherche utilisable | 0,14 s | 7 | 0 | 0 |
| HTML rendu | Source ajoutée, recherche utilisable | 10,42 s | 14 | 5 | 0 |
| Faux endpoint renvoyant l’accueil | Refus explicite, aucun ajout | 0,07 s | 4 | 0 | 0 |

Les requêtes de pages incluent celles effectuées dans les observations Chromium ; les deux colonnes ne s’additionnent pas. Aucun doublon n’est proposé dans ces quatre parcours. Le test dédié aux corrections identiques vérifie qu’aucun contrôle supplémentaire n’est exécuté pour une configuration déjà essayée. Ces durées de fixtures ne prédisent pas celles d’un site réel.

**Docker local non vérifié** : le démon Docker Desktop Linux est indisponible (`dockerDesktopLinuxEngine` absent). Aucun recours à Unraid n’a été effectué pour remplacer ce contrôle. Aucun site public supplémentaire n’a été validé.
