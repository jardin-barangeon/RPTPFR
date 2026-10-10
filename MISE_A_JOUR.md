# RPTPFR — Correctif administration

- Liste des challenges avec bouton **Actualiser la liste**, Modifier et Supprimer (confirmation).
- Champ **Webhook Discord** facultatif par challenge. Si vide, le Cron Job utilise `DISCORD_WEBHOOK_URL`.
- Migration automatique PostgreSQL : ajout de `discord_webhook` sans effacer les challenges existants.
- Les webhooks ne sont pas renvoyés par l’API publique.

## Installation Render
1. Sauvegarder le dépôt GitHub actuel, puis remplacer ses fichiers par ceux du ZIP.
2. Conserver toutes les variables secrètes déjà présentes dans Render (`DATABASE_URL`, `TRUCKY_TOKEN`, `ADMIN_PASSWORD_HASH`, `ADMIN_SESSION_SECRET`).
3. Vérifier la commande de build : `pip install -r requirements.txt`.
4. Redéployer le Web Service. Ouvrir `/admin`, se connecter et cliquer sur **Actualiser la liste**.
5. Mettre à jour également le Cron Job avec les nouveaux fichiers et garder le calendrier `0 10,11 * * *` (midi heure de Paris, vérifié dans le script).
6. Régénérer l'ancien webhook Discord déjà partagé dans le chat. Ne jamais le mettre sur GitHub.

Les rapports quotidiens sont ceux de la veille. Un rapport marqué envoyé n'est pas renvoyé automatiquement.
