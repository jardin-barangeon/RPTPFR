# Infos trafic Trucky — ETS2 Simulation 1

La page Infos trafic conserve les serveurs TruckersMP et ajoute les zones ayant `trafficJams > 0` depuis l’API Trucky.

- Route interne : `/api/trucky/traffic` (proxy Python, sans dépendance supplémentaire).
- Actualisation : 2 minutes lorsque l’onglet Infos trafic est affiché, ou bouton manuel.
- Si Trucky ne répond pas : message d’indisponibilité, jamais un faux « aucun bouchon ».
- Si aucun embouteillage : message de circulation sans embouteillage signalé.

Déploiement : remplacer les fichiers du dépôt GitHub par ceux du ZIP (sans modifier les variables Render), puis attendre le redéploiement.

Source : https://api.truckyapp.com/v2/traffic?game=ets2&server=sim1
