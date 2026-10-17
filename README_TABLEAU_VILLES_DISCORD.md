# Tableau des villes/secteurs — Discord ЯPTPFR

Cette version part du ZIP « Correctif doublons trafic Discord » fourni par l'utilisateur.

- Les alertes de bouchons restent dans leur présentation d'origine, sans filtre minimum de joueurs.
- Un seul message Discord supplémentaire récapitule les villes/secteurs ETS2 Simulation 1 où Trucky indique au moins 20 joueurs présents (`players`).
- De 20 à 50 joueurs : trafic modéré (orange). À partir de 51 : trafic important (rouge).
- Le tableau est actualisé toutes les 120 secondes et réutilise son message Discord ; les secteurs passés sous 20 joueurs disparaissent.
- Le tableau est supprimé si aucune zone ne compte 20 joueurs ou plus.
- Les identifiants des messages sont conservés en PostgreSQL ; aucun webhook supplémentaire n'est nécessaire.

**Note :** Les libellés sont ceux des localisations renvoyées par Trucky (villes ou secteurs). Les niveaux sont basés sur le nombre de joueurs présents, pas sur une mesure de vitesse réelle.

Déploiement : remplacer les fichiers sur GitHub, conserver `DATABASE_URL` et `TRAFIC_DISCORD_WEBHOOK_URL` dans Render, puis redéployer.
