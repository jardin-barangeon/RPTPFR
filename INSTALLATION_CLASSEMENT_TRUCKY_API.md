# Classement mondial Trucky

L’onglet « Classement mondial » utilise désormais l’API Trucky :
`https://e.truckyapp.com/api/v1/companies/leaderboards`

Paramètres : `game=1`, `stats_type=transport_system`, `country_code=`, `page=1`, `perPage=18`. Le mois et l’année sont calculés automatiquement en UTC.

Le serveur Python expose `/api/trucky/company-leaderboard`, avec cache de 5 minutes et proxy pour éviter CORS. La page recharge toutes les 5 minutes lorsque l’onglet est ouvert. En cas d’indisponibilité, une erreur est affichée et aucun classement fictif n’est utilisé.

Les classements des chauffeurs, challenges, missions, trafic, annonces Discord et autres routes ne sont pas modifiés. L’ancien endpoint `/api/world-rankings` reste disponible.
