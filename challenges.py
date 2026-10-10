import os, json, hmac, hashlib, secrets, time, datetime, urllib.parse, html
from http import cookies
from psycopg import connect
from psycopg.rows import dict_row

COOKIE='rptpfr_admin'
def db():
    url=os.getenv('DATABASE_URL','')
    if not url: raise RuntimeError('DATABASE_URL manquant : ajouter une base PostgreSQL Render.')
    return connect(url, row_factory=dict_row)
def setup():
    with db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS challenges (id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', transport TEXT NOT NULL CHECK(transport IN ('bus','camion','all')), mode TEXT NOT NULL CHECK(mode IN ('collectif','individuel')), target_km INTEGER NOT NULL CHECK(target_km>0), start_date DATE NOT NULL, end_date DATE NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), CHECK(end_date>=start_date))''')
def secret():
    s=os.getenv('ADMIN_SESSION_SECRET','')
    if len(s)<32: raise RuntimeError('ADMIN_SESSION_SECRET doit comporter au moins 32 caractères aléatoires.')
    return s.encode()
def password_ok(value):
    encoded=os.getenv('ADMIN_PASSWORD_HASH','')
    try:
        algorithm,iterations,salt,expected=encoded.split('$')
        if algorithm!='pbkdf2_sha256': return False
        derived=hashlib.pbkdf2_hmac('sha256',value.encode(),bytes.fromhex(salt),int(iterations))
        return hmac.compare_digest(derived.hex(),expected)
    except (ValueError,TypeError): return False
def make_cookie():
    expires=int(time.time())+8*3600
    nonce=secrets.token_hex(16)
    payload=f'{expires}.{nonce}'
    signature=hmac.new(secret(),payload.encode(),hashlib.sha256).hexdigest()
    return f'{payload}.{signature}'
def logged_in(handler):
    try:
        c=cookies.SimpleCookie();c.load(handler.headers.get('Cookie',''))
        raw=c[COOKIE].value
        exp,nonce,signature=raw.split('.')
        if int(exp)<time.time(): return False
        good=hmac.new(secret(),f'{exp}.{nonce}'.encode(),hashlib.sha256).hexdigest()
        return hmac.compare_digest(good,signature)
    except (KeyError,ValueError): return False
def cookie_header(value,maxage=28800):
    secure='; Secure' if os.getenv('RENDER') else ''
    return f'{COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={maxage}{secure}'
def check_origin(handler):
    origin=handler.headers.get('Origin','')
    host=handler.headers.get('Host','')
    scheme='https' if os.getenv('RENDER') else 'http'
    return origin==f'{scheme}://{host}' and bool(origin)
def read_json(handler):
    length=int(handler.headers.get('Content-Length','0'))
    if not 0<length<=10000: raise ValueError('Taille de requête invalide')
    return json.loads(handler.rfile.read(length))
def validate(data):
    title=str(data.get('title','')).strip()[:100]
    description=str(data.get('description','')).strip()[:500]
    transport=data.get('transport');mode=data.get('mode')
    target=int(data.get('target_km',0))
    start=datetime.date.fromisoformat(str(data.get('start_date','')))
    end=datetime.date.fromisoformat(str(data.get('end_date','')))
    if not title or transport not in ('bus','camion','all') or mode not in ('collectif','individuel') or not 1<=target<=100000000 or end<start:raise ValueError('Champs du challenge invalides')
    return title,description,transport,mode,target,start,end,bool(data.get('active',True))
def list_challenges():
    with db() as conn:
        return conn.execute('SELECT id,title,description,transport,mode,target_km,start_date,end_date,active FROM challenges ORDER BY start_date DESC,id DESC').fetchall()
def public_challenges(jobs):
    result=[]
    for c in list_challenges():
        if not c['active']:continue
        start=c['start_date'].isoformat();end=c['end_date'].isoformat()
        filtered=[j for j in jobs if start<=j.get('date','')[:10]<=end and (c['transport']=='all' or j.get('vehicle_type')==c['transport'])]
        totals={}
        for j in filtered:totals[j['driver']]=totals.get(j['driver'],0)+j['km']
        leaderboard=sorted([{'name':name,'km':round(km,2)} for name,km in totals.items()],key=lambda x:-x['km'])
        achieved=max(totals.values(),default=0) if c['mode']=='individuel' else sum(totals.values())
        result.append({**c,'start_date':start,'end_date':end,'progress_km':round(achieved,2),'leaderboard':leaderboard[:10],'participants':len(totals),'percent':round(min(100,achieved/c['target_km']*100),1)})
    return result
ADMIN_HTML=r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Administration Challenges RPTPFR</title><style>body{margin:0;background:#101b2e;color:#f4f7ff;font:16px system-ui}main{max-width:1050px;margin:auto;padding:30px 18px}a{color:#9bc2ff}h1{margin-bottom:6px}.panel{background:#1b2a42;border:1px solid #344760;border-radius:15px;padding:22px;margin:20px 0}input,select,textarea{box-sizing:border-box;width:100%;background:#101b2e;border:1px solid #526481;border-radius:8px;padding:11px;color:white;font:inherit}label{display:block;margin:10px 0}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}button{border:0;border-radius:9px;background:#4386e8;color:white;padding:11px 17px;font:inherit;cursor:pointer;margin:4px}button.danger{background:#ac4050}button.secondary{background:#445672}.item{padding:14px;border-bottom:1px solid #40506a}small{color:#b2c1d8}#message{min-height:20px;color:#ffc58a}@media(max-width:650px){.grid{grid-template-columns:1fr}}</style></head><body><main><a href="/">← Retour au site</a><h1>Administration des challenges</h1><p>Accès privé RPTPFR • Connexion sécurisée</p><div id="login" class="panel"><h2>Connexion</h2><label>Mot de passe administrateur<input id="password" type="password" autocomplete="current-password"></label><button id="connect">Se connecter</button></div><div id="dashboard" hidden><div class="panel"><button id="logout" class="secondary">Déconnexion</button><h2 id="formtitle">Nouveau challenge</h2><form id="form"><input type="hidden" id="id"><label>Nom du challenge<input id="title" required maxlength="100" placeholder="Défi 50 000 km BUS"></label><label>Description<textarea id="description" maxlength="500" rows="2"></textarea></label><div class="grid"><label>Transport<select id="transport"><option value="bus">BUS</option><option value="camion">CAMION</option><option value="all">BUS + CAMION</option></select></label><label>Type de challenge<select id="mode"><option value="collectif">Collectif</option><option value="individuel">Individuel</option></select></label><label>Objectif en kilomètres<input id="target_km" type="number" min="1" max="100000000" required></label><label>Début<input id="start_date" type="date" required></label><label>Fin<input id="end_date" type="date" required></label><label><input id="active" type="checkbox" checked style="width:auto"> Challenge visible</label></div><button type="submit">Enregistrer</button><button type="button" id="reset" class="secondary">Annuler</button></form></div><div class="panel"><h2>Challenges enregistrés</h2><div id="items"></div></div></div><p id="message" role="status"></p></main><script>const $=id=>document.getElementById(id);let entries=[];const fields=['title','description','transport','mode','target_km','start_date','end_date','active'];function msg(s){$('message').textContent=s}async function api(path,options={}){const r=await fetch(path,{credentials:'same-origin',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});let j=await r.json();if(!r.ok)throw Error(j.error||'Erreur serveur');return j}function show(yes){$('login').hidden=yes;$('dashboard').hidden=!yes}function reset(){$('form').reset();$('id').value='';$('formtitle').textContent='Nouveau challenge'}async function load(){try{const j=await api('/api/admin/challenges');entries=j.challenges;show(true);const root=$('items');root.replaceChildren();if(!entries.length)root.textContent='Aucun challenge pour le moment.';for(const c of entries){const div=document.createElement('div');div.className='item';const label=document.createElement('div');label.textContent=`${c.title} — ${c.target_km.toLocaleString('fr-FR')} km — ${c.transport.toUpperCase()} — ${c.mode} — ${c.start_date} → ${c.end_date}${c.active?'':' (masqué)'}`;div.append(label);const edit=document.createElement('button');edit.textContent='Modifier';edit.onclick=()=>{for(const f of fields)$(f).type==='checkbox'?$(f).checked=c[f]:$(f).value=c[f];$('id').value=c.id;$('formtitle').textContent='Modifier le challenge';window.scrollTo(0,0)};const del=document.createElement('button');del.className='danger';del.textContent='Supprimer';del.onclick=async()=>{if(!confirm('Supprimer définitivement ce challenge ?'))return;try{await api('/api/admin/challenges/'+c.id,{method:'DELETE',body:'{}'});await load()}catch(e){msg(e.message)}};div.append(edit,del);root.append(div)}}catch(e){show(false);msg(e.message)}}$('connect').onclick=async()=>{try{await api('/api/admin/login',{method:'POST',body:JSON.stringify({password:$('password').value})});$('password').value='';msg('');await load()}catch(e){msg(e.message)}};$('logout').onclick=async()=>{await api('/api/admin/logout',{method:'POST',body:'{}'});show(false);msg('Déconnecté')};$('reset').onclick=reset;$('form').onsubmit=async e=>{e.preventDefault();const obj={};for(const f of fields)obj[f]=$(f).type==='checkbox'?$(f).checked:$(f).value;try{const id=$('id').value;await api('/api/admin/challenges'+(id?'/'+id:''),{method:id?'PUT':'POST',body:JSON.stringify(obj)});reset();msg('Challenge enregistré');await load()}catch(e){msg(e.message)}};load();</script></body></html>'''
