# Validation partielle et export — 0.5.5-preview

La recherche, la reconnaissance des pages et la lecture ont des bilans séparés.
L'assistant conserve les deux recherches distinctes, le témoin vide, la répétition
stable et le contrôle de pagination. Il examine ensuite jusqu'à 20 destinations
par terme, dédupliquées. Une page non reconnue ne fait plus perdre les autres
observations et ne relance pas toute la recherche avec Chromium.

Chaque page indique son état : reconnue, supprimée, accès nécessaire, erreur
réseau, lecteur non reconnu, contenu non vidéo ou non contrôlée. L'absence de
métadonnées reste ambiguë. Les observations HTTP et Chromium sont mises en cache
uniquement pendant la tâche ; une reprise recharge les pages. L'échéance et
l'annulation conservent le bilan déjà enregistré et les pages restantes.

L'ajout automatique exige toutes les pages reconnues. **Ajouter avec validation
partielle** est disponible en fin de parcours si la recherche et la pagination
passent, avec au moins une page reconnue pour chaque terme, sans destination
identifiée comme contenu non vidéo. Le serveur vérifie le propriétaire, la
configuration, le moteur et des preuves de moins de 24 heures. Les mises à jour
vérifient aussi la configuration précédente et la sauvegardent. La qualification
partielle reste attachée à la source après expiration du rapport. Elle ne valide
ni l'extraction ni la lecture. Les anciennes tâches sans ces preuves doivent être
reprises pour permettre un ajout partiel.

**Exporter les résultats** télécharge un fichier ZIP, y compris pendant une
découverte. Il contient `resume.txt` en français et `diagnostic.json` versionné :
paramètres, candidat, bilans, contrôles, compteurs et tentative précédente.
Les titres, URL publiques et termes sont inclus. Les secrets, identifiants de
credentials, en-têtes, cookies, corps de requêtes et pages complètes sont exclus.
L'export n'envoie rien à un tiers et ne récupère pas les anciennes tentatives.

API : `POST /api/source-assistant/jobs/{id}/accept-partial` et
`GET /api/source-assistant/jobs/{id}/export`, réservés au propriétaire.
Les paramètres Unraid, Browserless et les secrets restent ceux de l'installation.
La table additive `source_validation` est incluse dans la sauvegarde SQLite.
Sauvegarder séparément la clé de chiffrement avant déploiement.

## Recette

Fixtures non explicites HTML, JSON et Chromium : découverte, bilan, ajout et
recherche normale. Fixture mixte : six pages reconnues, deux lecteurs non reconnus,
ajout partiel explicite, qualification persistante et ZIP ouvert/vérifié.
Les pages d'erreur et les résultats de secours restent refusés.
L'interface est contrôlée à 1400 et 390 pixels, en clair/sombre, au clavier,
avec fermeture/réouverture, annulation et téléchargement.

Commandes : suite `python -m unittest discover -s tests`, `node --check` pour les
scripts de l'application, garde-fou des dialogues natifs inclus dans les tests,
`git diff --check`, `scripts/check-source-diagnostics.py --browser` et
`scripts/check-source-diagnostics-ui.py`.

Sous Windows, 235 tests sur 236 passent ; le test de proxy réseau déjà défaillant
rencontre WinError 64. La suite complète doit passer en conteneur Linux avant
publication. Docker Desktop local étant indisponible, les images sont contrôlées
dans des conteneurs temporaires isolés sur Unraid, avant toute bascule.
Les mesures de cette recette portent sur des fixtures, pas sur un site public.
Aucune nouvelle compatibilité publique n'est annoncée.

## English

Search, destination recognition and playback have independent evidence. Up to
20 URLs per ordinary query are checked, deduplicated. Failed or ambiguous pages
do not erase successful checks. HTTP and rendered observations are reused within
one job only; resumed jobs fetch fresh evidence. Cancellation and deadlines keep
completed observations and pending counts.

Automatic addition requires every inspected destination to be recognized.
Explicit partial acceptance requires successful search/pagination, a recognized
page for each ordinary query and no confirmed non-video destination. The server
enforces ownership, configuration identity, engine revision and evidence younger
than 24 hours. Updates check and back up the previous connector. The partial
qualification survives job expiry and does not certify extraction or playback.

The export button downloads one ZIP with a French text summary and versioned
JSON, including running-job snapshots. Public URLs, titles and search terms are
included; credentials, headers, cookies, request bodies and raw pages are not.
There is no automatic upload. Existing Unraid/Browserless configuration remains
unchanged; back up SQLite, configuration and the encryption key before upgrading.

HTML, JSON, rendered HTML, mixed-page acceptance and negative fixtures are tested.
UI coverage includes keyboard export, mobile, both themes, reopening and stopping.
One pre-existing Windows proxy test fails with WinError 64; Linux container tests
are a release gate. Fixture success makes no claim of additional public-site support.

## Mesures de livraison

- Suite Linux des images finales : **236 tests réussis en 149,496 s**.
- Local Windows : 235/236, seul échec du proxy réseau préexistant (WinError 64).
- JavaScript, garde-fou des dialogues natifs et `git diff --check` : réussis.
- Recette UI : HTML, JSON, Chromium, ajout partiel (6 reconnues / 2 ambiguës),
  export terminal et actif, annulation, réouverture, clavier, 390/1400 px, clair/sombre.
  Un avertissement de fermeture Proactor Windows peut apparaître après les assertions.

Mesures locales des fixtures, découverte puis recherche normale :

| Parcours | Durée | Requêtes HTTP simulées | Observations navigateur | Édition manuelle |
|---|---:|---:|---:|---:|
| HTML | 1,257 s | 16 | 0 | 0 |
| JSON | 0,280 s | 16 | 0 | 0 |
| Mixte, ajout partiel explicite | 0,415 s | 16 | 0 | 0 |
| HTML rendu | 12,841 s | 17 | 6 | 0 |
| Accueil sans recherche (refus) | 0,161 s | 4 | 0 | 0 |
| Page d'erreur variable (refus) | 0,086 s | 3 | 0 | 0 |

Le cache est vérifié séparément : deux candidats examinant les mêmes six URL
produisent six lectures HTTP au total, contre douze sans réutilisation ; six
lectures sont évitées. Une reprise recharge les observations. Les fixtures de
recette n'ont pas de candidats identiques supplémentaires (compteur évité : 0).
Les durées ne constituent ni un objectif de performance sur Internet ni une preuve
de compatibilité publique. Le bilan de déploiement conserve le commit, les
sauvegardes, les contrôles publics et les limites.

Release measurements: 236 Linux tests passed in 149.496 seconds; the documented
Windows proxy failure remains. The local fixture table measures discovery plus
normal search, with no manual connector editing. Partial acceptance itself is an
explicit user action. Shared-page caching avoids six of twelve HTTP reads across
two candidates; resumed jobs fetch fresh evidence. No public-site claim follows
from these fixture measurements.
