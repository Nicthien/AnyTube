# AnyTube

- Projet de plateforme vidéo personnelle auto-hébergée avec Docker.
- Backend Python/FastAPI ; yt-dlp est le moteur d’extraction, FFmpeg le moteur média.
- Distinguer extraction par URL, recherche par plateforme et lecture navigateur.
- Ne jamais présenter un extracteur installé comme une compatibilité vérifiée.
- Aucun dialogue JavaScript natif : ne jamais appeler alert, confirm, prompt, ni leurs variantes window/globalThis/self. Utiliser des modales intégrées, accessibles, traduites et adaptées au mobile et aux thèmes.
- Vérifier avec `python -m unittest discover -s tests` et `git diff --check`.
- Maintenir le déploiement Docker et documenter précisément les fonctionnalités réellement disponibles.
