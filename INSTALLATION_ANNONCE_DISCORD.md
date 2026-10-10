# Correctif annonce Discord à la création — RPTPFR

Remplacer les fichiers du dépôt GitHub par ceux de cette archive, puis redéployer le Web Service Render.

À la création d’un challenge, une annonce Discord est envoyée immédiatement au webhook du challenge, ou à défaut à la variable `DISCORD_WEBHOOK_URL` du **Web Service** Render.

L’administration affiche le résultat : « Annonce Discord envoyée » ou une explication sans révéler l’URL secrète. Le challenge est conservé dans PostgreSQL même si Discord est indisponible.

Ce correctif **n’envoie pas d’annonce** à la modification d’un challenge, pour éviter les doublons. Les bilans quotidiens restent gérés séparément par `daily_discord.py` et le Cron Job Render à midi.

**Sécurité :** régénérer le webhook Discord précédemment partagé et remplacer son URL dans Render / les challenges concernés. Ne jamais committer les secrets dans GitHub.
