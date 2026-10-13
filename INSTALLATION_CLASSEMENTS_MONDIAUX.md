# Classements mondiaux Trucky — version expérimentale

1. Envoyer le contenu de ce dossier sur GitHub.
2. Render utilise `render.yaml` : l'installation de Chromium s'ajoute au build. Si Render utilise une commande de build personnalisée, la remplacer par : `pip install -r requirements.txt && python -m playwright install chromium`.
3. Une fois le déploiement terminé, ouvrir l'onglet « Classement mondial » du site. La première visite déclenche une lecture asynchrone. Les résultats sont conservés en mémoire une heure.

Limites : la page Trucky est une application JavaScript. Les sélecteurs du lecteur sont génériques et n'ont pas été validés contre une session réelle Trucky. Les tableaux qui ne sont pas publiquement lisibles ne sont pas inventés. Le rang de ЯPTPFR n'est affiché que si l'entreprise est présente dans les lignes récupérées. Si Trucky utilise des cartes au lieu de tableaux, une authentification, une API interne protégée ou une pagination non visible, une adaptation sera nécessaire.

En cas d'erreur, consulter les logs Render avec le préfixe `[TRUCKY MONDIAL]`. Le site et ses autres fonctions ne dépendent pas du lecteur mondial.
