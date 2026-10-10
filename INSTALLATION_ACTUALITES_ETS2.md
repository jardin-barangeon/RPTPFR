# RPTPFR — Actualités ETS2 + notifications Discord

## Site web

Remplacer `index.html` et `server.py` sur GitHub et ajouter `scs_news.py`. Garder `challenges.py`, `daily_discord.py`, les images et les autres fichiers. Le site affiche un onglet **Actualités ETS2** qui charge les annonces Steam du jeu ETS2.

## Notification automatique Discord

Dans Render, créer un **Cron Job** Python depuis le même dépôt GitHub :

- Build Command : `pip install -r requirements.txt`
- Command : `python scs_news.py`
- Schedule (UTC) : `*/15 * * * *` (vérification toutes les 15 minutes)
- Variables Environment du **Cron Job** : `DATABASE_URL` (URL PostgreSQL interne Render accessible depuis ce service) et `DISCORD_WEBHOOK_URL` (nouveau webhook Discord). Facultatif : `SCS_NEWS_WEBHOOK_URL` pour un salon distinct ; cette variable prend priorité sur le webhook global.

Le premier lancement mémorise les actualités déjà publiées **sans les annoncer**, afin de ne pas spammer Discord. Ensuite, chaque nouvel article ETS2 détecté déclenche une notification Discord avec le titre, un extrait et le lien. Un article n'est envoyé qu'une fois, grâce à PostgreSQL. Le message arrive à la prochaine vérification, **pas instantanément à la seconde de publication**.

**Important :** les variables du Web Service ne sont pas automatiquement transmises au Cron Job. Si vous avez déjà un Cron Job pour le classement à 12 h, gardez-le : celui-ci est un **deuxième Cron Job**, indépendant.

Le flux est fourni par l'API publique d'actualités Steam pour ETS2 (appid 227300). Il peut contenir des annonces de l'écosystème Steam du jeu, pas uniquement des billets du blog SCS. Le texte peut être en anglais. Si Steam ou Discord est indisponible, la vérification suivante réessaie les annonces non envoyées.

Ne placez jamais vos webhooks, mots de passe, tokens ou URL de base de données dans GitHub. Renouvelez le webhook précédemment partagé.
