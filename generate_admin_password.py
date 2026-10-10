import hashlib,secrets,getpass
password=getpass.getpass('Choisis un mot de passe administrateur (minimum 12 caracteres) : ')
if len(password)<12:raise SystemExit('Mot de passe trop court')
salt=secrets.token_bytes(16);rounds=350000
print('ADMIN_PASSWORD_HASH=pbkdf2_sha256$%s$%s$%s'%(rounds,salt.hex(),hashlib.pbkdf2_hmac('sha256',password.encode(),salt,rounds).hex()))
