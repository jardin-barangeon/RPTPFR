# Correctif bouton classement Discord

- Correction de la portée locale de `urllib` dans `server.py` : elle masquait la vraie erreur et renvoyait « Base de données ou configuration indisponible ».
- Correction de l’accès au résultat PostgreSQL dans `daily_discord.py` : le curseur `dict_row` renvoie un dictionnaire, pas un tuple.

Installer le ZIP complet sur GitHub, attendre Render Live, puis réessayer le bouton. Si une autre erreur apparaît, consulter les logs Render pour la ligne `[TEST CLASSEMENT DISCORD]`.

Les notifications automatiques dépendent du Web Service actif à midi.
