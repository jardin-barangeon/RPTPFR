# TOP 5 mensuel CAMION / BUS — Discord

Le rapport automatique est tenté chaque jour à partir de **12 h, heure de Paris**, par le Web Service Render (sans Cron Job). Le bouton existant `/admin` envoie le **même TOP 5 mensuel** à la demande.

Pour chaque catégorie, le cumul va du **1er jour du mois de la veille** jusqu'à la **veille incluse** : un rapport du 13 octobre porte sur les missions du 1er au 12 octobre. Le 1er novembre, le rapport couvre le mois d'octobre (veille = 31 octobre) ; le 2 novembre, il couvre le 1er novembre.

Les bilans des challenges restent basés sur leurs dates et sur les kilomètres de la veille. Le classement public du site et les annonces manuelles ne changent pas.

## Installation
1. Remplacer les fichiers du dépôt GitHub par ceux de ce ZIP (sans modifier les variables Render).
2. Attendre le statut **Live** de Render.
3. Ouvrir `/admin`, puis cliquer sur **Envoyer le classement BUS/CAMION maintenant**.
4. Vérifier que Discord affiche `TOP 5 mensuel` et la plage de dates.

**Limite existante** : si Render met le Web Service en veille, l'envoi automatique ne peut pas être garanti à midi. Les données dépendent également de l'historique de missions réellement fourni par l'API Trucky ; un avertissement est affiché lorsqu'il peut être incomplet.
