# Notifications Discord à midi sans Cron Job

Cette version lance automatiquement le rapport BUS/CAMION depuis `server.py`.

1. Remplacer les fichiers du dépôt GitHub par ceux de cette archive.
2. Vérifier les variables du **Web Service Render** : `TRUCKY_TOKEN`, `DATABASE_URL`, `DISCORD_WEBHOOK_URL`.
3. Redéployer le Web Service et consulter ses **Logs**. Chercher `[DISCORD QUOTIDIEN] Programmateur interne démarré`.
4. Chaque jour, à partir de 12 h **Europe/Paris**, le site tente d'envoyer le classement de la veille. En cas d'échec, il réessaie au plus toutes les 15 minutes.
5. Une ligne dans la base PostgreSQL évite de renvoyer le même rapport plusieurs fois. Un verrou PostgreSQL limite les doublons si plusieurs instances tournent.

**Attention :** sur un Web Service Render mis en veille, arrêté ou inaccessible à midi, aucun programme ne peut tourner. L'envoi sera tenté au réveil du service après midi, s'il redémarre le jour même. Pour un horaire garanti, un plan toujours actif ou un service de planification externe reste nécessaire.

Le bouton de message Discord manuel dans `/admin` et toutes les autres fonctionnalités sont conservés.
