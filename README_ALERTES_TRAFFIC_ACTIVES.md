# Alertes trafic Discord : uniquement les bouchons en cours

Le webhook `TRAFIC_DISCORD_WEBHOOK_URL` reste inchangé dans Render.
Toutes les 2 minutes, le système compare les bouchons ETS2 Simulation 1 :
- Nouveau bouchon : publication d'un message Discord.
- Nombre de bouchons / joueurs modifié : édition du message existant.
- Bouchon disparu de l'API Trucky : suppression du message Discord.
- API Trucky inaccessible : conservation des messages (aucune suppression par erreur).

**Limitation importante :** les identifiants des messages sont gardés en mémoire. Après un redémarrage Render, les anciens messages déjà publiés ne peuvent pas être retrouvés/supprimés automatiquement par un webhook seul. Nettoyez les anciens messages une fois lors de l'installation ; en fonctionnement continu, les nouveaux messages sont synchronisés. Les alertes créées par l'ancienne version ne sont pas gérées rétroactivement.
