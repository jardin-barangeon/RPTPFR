# RPTPFR — Challenges administrables sur Render

Cette version conserve le tableau de bord Trucky existant et ajoute `/admin` et les challenges publics sur la page d’accueil.

## Déploiement

1. **Sauvegarde ton dépôt GitHub actuel** puis remplace/ajoute les fichiers de cette archive à la racine de ce même dépôt. Ne publie jamais `config.json`, le token Trucky, ou un mot de passe.
2. Sur Render, crée une base **Postgres** (Render Dashboard → New → Postgres). Choisis une offre et une région adaptées. La base doit être **persistante** : vérifie les limites de durée et le tarif de ton offre. Dans la page de la base, copie l’**Internal Database URL**.
3. Dans Render → ton Web Service → Environment, ajoute :
   - `DATABASE_URL` = Internal Database URL de Postgres
   - `TRUCKY_TOKEN` = ton token Trucky renouvelé (déjà configuré si le site marche)
   - `ADMIN_PASSWORD_HASH` = valeur produite par `python generate_admin_password.py` (sans `ADMIN_PASSWORD_HASH=`)
   - `ADMIN_SESSION_SECRET` = une longue chaîne aléatoire d’au moins 32 caractères (générer localement : `python -c "import secrets;print(secrets.token_urlsafe(48))"`)
4. Dans Render → Settings, configure **Build Command** : `pip install -r requirements.txt` et **Start Command** : `python server.py`. Si tu utilises un Blueprint `render.yaml`, les commandes sont déjà prévues.
5. Déploie. Le serveur initialise automatiquement la table Postgres `challenges` au démarrage.
6. Ouvre `https://rptpfr.onrender.com/admin` pour te connecter et créer ton premier défi. Les défis actifs apparaissent sur la page publique.

## Sécurité

- Le mot de passe n’est pas stocké en clair, seulement son empreinte PBKDF2 dans les variables Render.
- Cookie signé HMAC, HttpOnly, SameSite=Strict, Secure sur Render, expiration 8 heures.
- Les modifications exigent une session valide et une requête provenant de la même origine HTTPS.
- Ne mets jamais les secrets dans GitHub. En cas de compromission, renouvelle le token Trucky et le secret de session.
- Ce compte administrateur unique est adapté à une petite équipe. Pour des comptes multiples et une protection anti-bruteforce robuste, utiliser une solution d’authentification dédiée et un filtrage réseau.
- Les challenges comptabilisent les livraisons selon les données Trucky actuellement récupérées, pas nécessairement les points officiels des classements.
- Si Render n’est pas encore configuré avec PostgreSQL, le nouveau serveur ne démarre pas : prépare les variables avant le déploiement.
