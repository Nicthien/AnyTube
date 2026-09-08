# Sessions de sites et réseau sortant

Le [bilan de validation 0.6.0](VALIDATION-0.6.0.md) décrit les parcours contrôlés. Cette évolution ne constitue pas une annonce de compatibilité avec un site public particulier.

## Session interactive

Depuis une découverte ou une source, **Ouvrir la session** affiche Chromium dans une modale AnyTube. L’adresse reste visible. Les clics et le clavier sont transmis au site ; Échap rend le focus aux commandes AnyTube. Un champ de saisie complémentaire permet d’utiliser le clavier mobile. Les QR codes affichés par le site font partie de l’écran distant.

L’utilisateur effectue lui-même les vérifications. AnyTube ne valide pas automatiquement l’âge et ne simule pas une vérification réussie. Caméra, microphone, fenêtres secondaires et WebSockets du site ne sont pas pris en charge. Les redirections de navigation GET et POST vers GET sont relayées ; une redirection exigeant de rejouer un téléversement reste refusée. Ces limites peuvent empêcher certaines connexions ou vérifications.

**Enregistrer la session et reprendre** conserve les cookies, le stockage local et IndexedDB du site sélectionné, chiffrés dans le coffre existant. Le stockage des autres sites reste éphémère. `sessionStorage` n’est pas restauré. Le délai maximal est de 30 jours après une validation explicite, sans prolongation par les recherches. Le site peut expirer sa session plus tôt. Une session interactive inactive est fermée après 15 minutes ; au maximum une session ouverte par compte et deux sur le serveur. Les sessions enregistrées se renouvellent et se suppriment depuis **Sessions des sites**.

Pour un fichier, sélectionner d’abord le champ de téléversement du site, puis choisir explicitement un PDF, JPEG ou PNG de 20 Mio maximum dans AnyTube. Le fichier est transmis en mémoire. Le service efface sa copie après transfert ; le champ Chromium peut la conserver jusqu’à l’envoi du formulaire ou la fermeture du contexte. Aucun fichier, frappe ou écran n’est ajouté aux diagnostics.

La reprise recharge les réponses et refait les contrôles avec le budget restant. Les cookies peuvent être utilisés par les recherches et les workers ; les clés du service navigateur ne leur sont pas transmises. Une authentification qui repose exclusivement sur un contexte JavaScript ne rend pas automatiquement l’extraction yt-dlp possible. Recherche, reconnaissance des pages, extraction et lecture restent des capacités séparées.

## Chromium intégré dans Compose

Fusionner `compose.unraid.yaml` et `compose.interactive.yaml`. Configurer côté serveur deux secrets distincts : `ANYTUBE_INTERACTIVE_TOKEN` et `ANYTUBE_BROWSER_EGRESS_TOKEN`. Ne pas les ajouter à Git. Aucun port du navigateur ni de CDP n’est publié. Les fichiers et profils temporaires restent dans les systèmes de fichiers en mémoire du conteneur.

Le profil `deploy/chromium-seccomp.json`, issu de Playwright 1.62, autorise les espaces de noms nécessaires à la sandbox Chromium. Il ne faut pas remplacer la sandbox par `--no-sandbox`. Si Compose s’exécute depuis un autre dossier, renseigner `ANYTUBE_CHROMIUM_SECCOMP` avec le chemin absolu du profil. Le conteneur navigateur résout uniquement l’adresse de sa passerelle Docker au démarrage, puis bloque ses sorties DNS et toute connexion hors de cette passerelle.

L’observateur Browserless existant reste configuré. Le moteur utilise Chromium intégré pour les sessions, lorsqu’aucun observateur n’est configuré et en mode proxy/VPN. Les préférences Browserless enregistrées restent conservées.

## Proxy et VPN

**Réseau sortant**, réservé à l’administrateur, propose Direct, Proxy HTTP/HTTPS et VPN intégré. Direct reste la valeur initiale. Aucun fournisseur n’est activé automatiquement.

Le proxy est configuré avec une adresse IP et un port, afin d’éviter une résolution de son nom hors du trajet choisi. Un proxy HTTPS peut recevoir un nom de certificat distinct ; sa chaîne TLS reste vérifiée. Les identifiants sont chiffrés côté serveur. Le test affiche la disponibilité et l’adresse publique constatée ; il ne remplace pas une recette de tous les flux.

En proxy/VPN, les noms publics sont résolus par DNS sur HTTPS à travers le proxy, puis les connexions CONNECT ciblent les adresses numériques contrôlées. Une adresse privée, une résolution mixte publique/privée ou un port public autre que 80/443 est refusé. Aucun retour automatique vers Direct n’est prévu. Les services internes explicitement configurés restent accessibles par le proxy administratif.

La lecture et les sous-titres passent par les routes média AnyTube ; les miniatures sont également relayées. Les cadres tiers et les chargements média directs sont bloqués par la politique du frontend. Un changement de trajet invalide les connexions et les sessions doivent être recontrôlées. L’interface reste disponible si le trajet public tombe.

### Passerelle Gluetun facultative

Ajouter `compose.vpn.yaml` uniquement après avoir préparé les paramètres serveur. Le service reste derrière le profil Compose `vpn`. Il utilise `qmcgaw/gluetun:v3.41.3`, sans port publié, avec son pare-feu activé.

- `ANYTUBE_VPN_TYPE` : `wireguard` ou `openvpn`.
- `ANYTUBE_VPN_CONFIG` : chemin absolu du fichier serveur `vpn.conf`.
- `ANYTUBE_VPN_SUBNET` et `ANYTUBE_VPN_IP` : réseau Docker dédié, sans conflit avec les réseaux existants ; valeurs initiales `172.30.90.0/24` et `172.30.90.3`.
- OpenVPN : `ANYTUBE_OPENVPN_USER` et `ANYTUBE_OPENVPN_PASSWORD`, si le fournisseur les exige.
- Proxy Gluetun : `ANYTUBE_VPN_PROXY_USER` et `ANYTUBE_VPN_PROXY_PASSWORD`, facultatifs.

Le service `vpn-config` valide la configuration avant de la placer dans le volume partagé. Les directives OpenVPN de scripts, plugins, gestion distante et inclusions arbitraires sont refusées. Utiliser des certificats et clés inline ; les références à des fichiers externes sont refusées. WireGuard accepte une interface et un pair ; les hooks système sont refusés. Ces exemples décrivent le format, sans fournir de clé ni de fournisseur :

```ini
[Interface]
PrivateKey = <clé privée du fournisseur>
Address = <adresse du tunnel>/32
[Peer]
PublicKey = <clé publique du serveur>
Endpoint = <IP du serveur>:51820
AllowedIPs = 0.0.0.0/0
```

```text
client
dev tun
proto udp
remote <IP du serveur> 1194
remote-cert-tls server
<ca>
<certificat CA fourni>
</ca>
```

Après démarrage explicite du profil, choisir VPN dans AnyTube, saisir l’adresse du proxy Gluetun, normalement `http://172.30.90.3:8888`, puis tester. Le protocole affiché dans AnyTube décrit le service configuré ; il ne réécrit pas les paramètres du fournisseur.

## Diagnostic et validation

L’export ZIP conserve les états d’accès, de session et la révision réseau, mais exclut l’identifiant donnant accès à une session, les cookies, stockages, fichiers, écrans et secrets. Les termes et URL publiques restent inclus.

Scripts de recette : `scripts/check-interactive-browser.py`, `scripts/check-source-diagnostics.py`, `scripts/check-source-diagnostics-ui.py`, `scripts/check-network-route.py` et `scripts/check-integrated-stack.py`. Ce dernier refuse un environnement autre que `validation-060` et crée un compte éphémère : ne jamais l’exécuter sur les données de production.

La publication est conditionnée au bilan de recette complet, notamment aux tests de panne et d’isolation. Un résultat sur fixture ne garantit ni la compatibilité d’un site ni l’acceptation de son contrôle d’âge dans un navigateur distant.
