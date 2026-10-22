# Correctif anti-rafales Discord — 22 octobre 2026

- Surveillance Trucky : toutes les 120 secondes.
- Trafic : maximum une écriture Discord par cycle au lieu de huit.
- Tableau des villes : mise à jour alternée pour réduire les rafales.
- Vérification de la pause PostgreSQL avant chaque requête Discord.
- Enregistrement des messages déjà envoyés avant un éventuel arrêt sur HTTP 429.
- Aucun changement des classements, défis ou présentation des messages.

Attention : si Cloudflare limite l'IP partagée de Render, aucun correctif applicatif ne garantit la levée du blocage. Attendre la fin du Retry-After et vérifier les logs.
