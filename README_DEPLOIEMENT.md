# RPTPFR sur Render

Ce paquet reprend le site RPTPFR avec sa bannière, son logo, son TOP 3 BUS et CAMION, et sa récupération Trucky. Aucun token n’est inclus.

## Mise en ligne
1. Révoquer le token Trucky déjà partagé et en créer un nouveau.
2. Créer un dépôt **privé** sur GitHub et y déposer le contenu de ce dossier (les fichiers doivent être à la racine). Ne jamais déposer `config.json`, `.env` ou un token.
3. Sur https://dashboard.render.com, choisir **New > Web Service**, puis connecter ce dépôt GitHub.
4. Choisir le runtime **Python 3** et une offre payante sans mise en veille (Starter, sous réserve des tarifs en vigueur).
5. Build Command : `echo Installation sans dependances externes`
6. Start Command : `python server.py`
7. Dans **Environment**, ajouter `TRUCKY_TOKEN` avec le nouveau token. Ne jamais l'inscrire dans GitHub ou le code.
8. Déployer. Tester `/health`, puis la page principale et le filtre BUS pour octobre.
9. L'adresse publique sera fournie par Render au format `https://...onrender.com`.

**Alternative Blueprint** : le fichier `render.yaml` contient la configuration, avec un secret `TRUCKY_TOKEN` à renseigner dans Render.

## Fonctionnement et limites
- Le serveur écoute le port `PORT` de Render sur `0.0.0.0` en production.
- L'API Trucky est appelée par le serveur Python uniquement ; le navigateur ne voit pas le token.
- Cache en mémoire de 5 minutes, réinitialisé lors d'un redémarrage/déploiement.
- Ce serveur HTTP Python standard convient à un petit tableau de bord. Pour une audience importante, prévoir un serveur de production WSGI/ASGI et des contrôles de charge.
- Les chiffres de Trucky peuvent différer de leur classement officiel selon les règles de calcul.
- Un service gratuit Render peut se mettre en veille : choisir une formule payante pour la disponibilité permanente.
- Ne pas publier de fichiers secrets ni activer d'indexation de dossier.
