# RPTPFR — Discord automatique

1. Sur Discord, crée un **nouveau webhook** (le précédent a été exposé dans une conversation).
2. Sur Render > Web Service RPTPFR > Environment, ajoute `DISCORD_WEBHOOK_URL` avec l’URL du nouveau webhook.
3. Si tu utilises un Cron Job Render pour les bilans de midi, ajoute aussi `DISCORD_WEBHOOK_URL` dans son propre Environment.
4. Remplace les fichiers du dépôt GitHub par ceux de ce ZIP et redéploie. Conserve les valeurs existantes de `DATABASE_URL`, `TRUCKY_TOKEN`, `ADMIN_PASSWORD_HASH`, `ADMIN_SESSION_SECRET` sur Render.
5. Ouvre `/admin` et crée un **nouveau** challenge : l’annonce est envoyée immédiatement. L’administration affiche le résultat de l’envoi.

Le champ webhook n’existe plus dans le formulaire ; tous les challenges utilisent le webhook général de Render, y compris ceux qui avaient un webhook individuel auparavant. Les données PostgreSQL sont conservées.

**Important** : une annonce n’est envoyée que lors de la création, pas lors d’une modification. Les bilans quotidiens nécessitent toujours que le Cron Job soit configuré et exécuté.
