# Annonces publiques ЯPTPFR

- Dans `/admin`, envoyer un message avec « Envoyer sur Discord ».
- Le message est envoyé à Discord puis enregistré en base PostgreSQL.
- Les 5 annonces les plus récentes apparaissent au-dessus des classements sur la page d’accueil, actualisées toutes les 60 secondes.
- Les annonces existantes sur Discord avant cette mise à jour ne sont pas importées rétroactivement.
- Aucun nouveau paramètre Render : utilise `DATABASE_URL` et `DISCORD_WEBHOOK_URL` existants.
- Si Discord accepte le message mais que la base est indisponible, l’interface avertit que l’annonce n’a pas été publiée sur le site.
- Les messages sont affichés en texte brut, sans HTML exécutable.
