# Test manuel du classement Discord

Dans `/admin`, deux fonctions distinctes sont conservées :
- **Message aux chauffeurs** : envoyer un texte libre, avec mention @everyone facultative.
- **Test du classement quotidien BUS/CAMION** : envoyer immédiatement le vrai rapport de la veille (et bilans des challenges) sur le webhook Discord configuré.

Le bouton de test n’inscrit pas le rapport dans la table des envois automatiques : il ne bloque donc pas le rapport prévu à midi. Cliquer plusieurs fois peut envoyer plusieurs messages.

Le programmateur interne au Web Service reste actif. Sur une instance Render en veille, l’envoi automatique peut être retardé jusqu’au réveil du site.

Déployer tous les fichiers sur GitHub et attendre la fin du déploiement Render. Vérifier que `DISCORD_WEBHOOK_URL`, `TRUCKY_TOKEN` et `DATABASE_URL` sont configurés sur le Web Service.
