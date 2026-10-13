# RPTPFR — Classements quotidiens Discord à midi

Le fichier `daily_discord.py` envoie chaque jour à **12 h, heure de Paris**, les classements des missions terminées **la veille**, séparés CAMION et BUS (TOP 10, km, nombre de missions et de chauffeurs). Il ajoute ensuite les bilans des challenges actifs, s'il y en a.

## Configuration Render

Il faut un **Cron Job distinct du Web Service**. Le dépôt GitHub et le fichier `daily_discord.py` doivent être à jour sur ce Cron Job.

- **Build Command** : `pip install -r requirements.txt`
- **Command** : `python daily_discord.py`
- **Schedule (UTC)** : `0 10,11 * * *`
- **Environment du Cron Job** : `TRUCKY_TOKEN`, `DATABASE_URL`, `DISCORD_WEBHOOK_URL` (les mêmes valeurs valides que celles de votre Web Service).

Render programme en UTC. Le script vérifie `Europe/Paris` : l'exécution de 10 h UTC correspond à midi en été et celle de 11 h UTC à midi en hiver. L'autre exécution ne publie rien. Le rapport de chaque date n'est envoyé qu'une fois grâce à la table PostgreSQL `discord_daily_reports`.

## Vérification

Consulter les logs du **Cron Job** (et non du Web Service) autour de 10 h/11 h UTC. Chercher `Classements BUS/CAMION et bilans des challenges envoyes` ou le message d'erreur.

Un lancement manuel hors de midi ne publie rien par sécurité. Pour tester ponctuellement hors horaire, définir temporairement `ALLOW_MANUAL_RUN=1` dans l'environnement du Cron Job, exécuter une fois, puis supprimer cette variable. Un jour déjà envoyé ne sera pas renvoyé automatiquement.

**Attention** : l'API Trucky peut fournir un historique incomplet. Dans ce cas, le message Discord signale que les résultats sont indicatifs. Les missions sans date de fin exploitable ne peuvent pas être comptabilisées.

Ne pas publier le token Trucky ni l'URL du webhook Discord.
