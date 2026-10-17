# Alertes trafic Discord (façon Coyote)

1. Déployer cette archive sur GitHub, puis Render.
2. Dans Render > service Web > Environment, ajouter la variable `TRAFIC_DISCORD_WEBHOOK_URL` et y coller **l'URL de votre webhook Discord** (ne pas la mettre dans GitHub).
3. Sauvegarder et redéployer/redémarrer le service.
4. Vérifier les logs : `[ALERTES TRAFIC] Surveillance démarrée` puis `[ALERTES TRAFIC] Vérification terminée`.

Le serveur surveille ETS2 Simulation 1 toutes les deux minutes. Il notifie les nouveaux bouchons et les aggravations (plus de bouchons ou au moins 5 joueurs supplémentaires). Les alertes affichent l'heure de Paris, la route, le pays, les bouchons et les joueurs impliqués. Il n'envoie pas de message quand tout est fluide. Après un redémarrage, l'état en mémoire est réinitialisé : les bouchons encore présents peuvent être annoncés à nouveau.

**Sécurité :** l'URL webhook étant un secret, régénérez-la dans Discord si elle a été partagée publiquement.
