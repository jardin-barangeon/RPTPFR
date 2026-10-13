# Correctif Chromium Render

Ce correctif installe automatiquement Chromium au premier accès si le paquet Python Playwright est présent mais que le navigateur manque. Le premier chargement peut prendre plusieurs minutes.

Pour éviter ce délai, dans Render > Web Service > Settings > Build Command, mettre :

`pip install -r requirements.txt && python -m playwright install chromium`

Enregistrer puis lancer **Manual Deploy > Clear build cache & deploy**.

Si le service utilise un fichier render.yaml via Blueprint, sa commande de build inclut déjà cette installation. En cas d'erreur sur des bibliothèques système, utiliser un runtime Docker ou installer les dépendances Chromium compatibles avec le plan Render.

Ne pas installer Chromium sur votre ordinateur : seul Render en a besoin.
