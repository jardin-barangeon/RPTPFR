# RPTPFR — Bilan quotidien Discord

## 1. Mot de passe administrateur
Dans Render > Web Service > Environment, remplacez `ADMIN_PASSWORD_HASH` par la valeur contenue dans `ADMIN_HASH_RENDER.txt`. Le mot de passe demandé est `admin2206`. **Il est faible et a été partagé : remplacez-le dès que possible** en régénérant un hash avec `generate_admin_password.py`.

## 2. Créer le webhook Discord
Sur le serveur Discord : Paramètres du salon > Intégrations > Webhooks > Nouveau webhook > Copier URL. **Ne partagez jamais cette URL**.

## 3. Publier les fichiers
Copier les fichiers dans le dépôt GitHub privé RPTPFR et laisser Render redéployer le Web Service existant. La page `/admin` et le site public restent inchangés.

## 4. Créer une tâche Render Cron Job
Dans Render : New > Cron Job, même dépôt et même branche que le site.
- Runtime : Python
- Build Command : `pip install -r requirements.txt`
- Command : `python daily_discord.py`
- Schedule (UTC) : `0 10,11 * * *` (10h et 11h UTC ; le script envoie uniquement à 12h heure de Paris, été comme hiver)
- Variables d'environnement : `TRUCKY_TOKEN`, `DATABASE_URL` (même base PostgreSQL que le site), `DISCORD_WEBHOOK_URL` (URL du webhook Discord)

Render Cron Jobs peuvent être facturés selon le plan et la consommation. Ne pas ajouter l'URL du webhook dans GitHub.

Le script envoie le bilan **de la veille**, calculé en date française (Europe/Paris), pour chaque challenge actif durant cette journée. Le classement est établi sur les kilomètres du jour, avec progression cumulée depuis le début du challenge. Il ne renvoie pas un rapport déjà marqué envoyé pour cette date. Un échec entre envoi et écriture en base peut exceptionnellement produire un doublon lors d'une relance.

**Attention** : les kilomètres reposent sur les dates et distances renvoyées par l'API Trucky, et peuvent différer des classements officiels. Le script bloque l'envoi si l'API signale un historique potentiellement incomplet. Pour des rapports à heure fixe en France toute l'année, il faut ajuster le cron lors du changement d'heure ou utiliser un ordonnanceur qui gère le fuseau horaire.

## 5. Tester
Dans la tâche Cron Job, lancer `Trigger Run` pour vérifier la configuration. Si aucun challenge n'était actif hier, aucun message n'est envoyé. Consultez les logs Render. Ne publiez pas les secrets ni les logs contenant des URL privées.

## Sécurité du webhook
Le webhook partagé dans une conversation doit être régénéré dans Discord. Placez uniquement la nouvelle URL dans la variable secrète `DISCORD_WEBHOOK_URL` de la tâche Cron Job Render, jamais dans les fichiers du dépôt.
