# Correctif des doublons d'alertes trafic Discord

Les identifiants des messages sont désormais conservés dans PostgreSQL (`DATABASE_URL`). Les redémarrages Render ne doivent plus créer de doublons pour les bouchons encore actifs. Un verrou PostgreSQL évite que deux instances publient simultanément.

Le programme met à jour le message quand les données changent et le supprime quand la zone n'a plus de bouchon. Vérification toutes les 120 secondes.

**À faire une seule fois :** supprimer manuellement dans Discord les anciens doublons publiés par la version précédente. Un webhook Discord ne permet pas de retrouver/lister les messages anciens dont l'identifiant n'a pas été enregistré ; le programme ne peut donc pas les effacer automatiquement.

**Render :** conserver `TRAFIC_DISCORD_WEBHOOK_URL` et `DATABASE_URL` existants. Redéployer. Dans les logs, chercher `Synchronisation persistante PostgreSQL démarrée`.
