# Messages Discord depuis /admin

- Remplacer les fichiers du dépôt GitHub par le contenu de ce ZIP.
- Attendre le déploiement du Web Service Render.
- Dans **Render > Web Service > Environment**, configurer `DISCORD_WEBHOOK_URL` avec le même webhook que celui utilisé par le Cron Job. Les variables d'environnement du Cron Job ne sont pas automatiquement partagées avec le Web Service.
- Ouvrir `/admin`, se connecter et utiliser « Message aux chauffeurs sur Discord ».
- Faire un premier essai sans cocher « Mentionner @everyone ». Une confirmation précède chaque envoi.

Le test confirme que le **Web Service** peut envoyer un message sur le webhook. Il ne teste pas à lui seul le déclenchement horaire du Cron Job `daily_discord.py`, ni son accès à Trucky et à PostgreSQL.

Pour une vraie notification @everyone, le salon Discord et le webhook doivent autoriser cette mention. Les mentions écrites dans le texte sont neutralisées ; seule la case dédiée peut activer @everyone.
