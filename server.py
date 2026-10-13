import json, os, urllib.request, urllib.error, datetime, http.server, socketserver
import challenges
import scs_news
from pathlib import Path
ROOT=Path(__file__).parent
CONFIG=ROOT/'config.json'
HTML=(ROOT/'index.html').read_bytes()
def pick(obj,*keys):
    for key in keys:
        cur=obj
        for part in key.split('.'):
            cur=cur.get(part) if isinstance(cur,dict) else None
        if cur is not None: return cur
    return None
def vehicle_type(job):
    # TruckersMP: les trajets BUS sont identifies par la cargaison Passagers.
    # Ne pas se fier au type de vehicule (souvent "truck" meme pour un bus).
    import unicodedata
    fields=(
        'cargo', 'cargo_name', 'cargoName', 'cargo.name', 'cargo.title',
        'cargo.display_name', 'cargo.displayName', 'cargo.type',
        'cargo_data.name', 'cargoData.name', 'cargo_details.name',
        'job.cargo', 'job.cargo.name', 'job.cargo_name',
        'load', 'load.name', 'freight', 'freight.name',
        'trailer.cargo', 'trailer.cargo.name', 'shipment.cargo.name',
        'transport.cargo.name', 'goods', 'goods.name'
    )
    values=[]
    for field in fields:
        value=pick(job,field)
        if isinstance(value,dict):
            value=pick(value,'name','title','display_name','displayName','label')
        if isinstance(value,str) and value.strip():
            values.append(value.strip())
    if not values:
        return 'inconnu'
    for value in values:
        plain=''.join(c for c in unicodedata.normalize('NFKD',value.casefold()) if not unicodedata.combining(c))
        if 'passager' in plain or 'passenger' in plain:
            return 'bus'
    return 'camion'

def city_label(value):
    """Extrait un nom de ville des objets de localisation Trucky."""
    if isinstance(value, str):
        return value.strip()[:120]
    if isinstance(value, dict):
        for key in ('city', 'city_name', 'cityName', 'name', 'label', 'title', 'location', 'place'):
            found = city_label(value.get(key))
            if found:
                return found
    return ''

def find_city(job, paths):
    for path in paths:
        value = pick(job, path)
        city = city_label(value)
        if city:
            return city
    return ''

def normalize(payload):
    if isinstance(payload,list): jobs=payload
    elif isinstance(payload,dict):
        jobs=next((payload[k] for k in ('jobs','data','results','items') if isinstance(payload.get(k),list)),None)
        if jobs is None and isinstance(payload.get('data'),dict):
            jobs=next((payload['data'][k] for k in ('jobs','items','results') if isinstance(payload['data'].get(k),list)),None)
        if jobs is None: raise ValueError('Format de réponse Trucky non reconnu (liste des trajets introuvable).')
    else: raise ValueError('Réponse Trucky invalide.')
    out=[]; ignored=0
    for j in jobs:
        if not isinstance(j,dict): continue
        status=str(pick(j,'status','state') or '').lower()
        if status in ('canceled','cancelled','deleted','started','in_progress','in-progress'): continue
        driver=pick(j,'steam_profile.steam_username','user.steam_profile.steam_username','driver.steam_profile.steam_username','driver.username','user.username','driver.name','user.name','steam_username','username')
        distance=pick(j,'distance_km','distanceKm','distance.km','distance','driven_distance','drivenDistance','kilometers','km')
        unit=str(pick(j,'distance_unit','distanceUnit') or '').lower()
        try:
            if isinstance(distance,dict): distance=pick(distance,'value','km')
            km=float(str(distance).replace(',','.'))
            if unit in ('mi','miles'): km*=1.609344
            if not (0 <= km <= 100000): raise ValueError()
        except (ValueError,TypeError): ignored+=1; continue
        if not driver: ignored+=1; continue
        date=str(pick(j,'completed_at','completedAt','finished_at','finishedAt','delivery_date','date','created_at','createdAt') or '')
        cargo=pick(j,'cargo.name','cargo.title','cargo_name','cargoName','cargo','cargo_data.name','cargoData.name','job.cargo.name','job.cargo','goods.name')
        if isinstance(cargo,dict):cargo=pick(cargo,'name','title','label')
        origin=find_city(j, (
            'source_city.name','sourceCity.name','origin.city.name','origin.name','origin_city','originCity',
            'from_city.name','fromCity.name','from_city','source_city','departure_city.name','departureCity.name',
            'source.city.name','source.city','source.name','source','departure.city.name','departure.city',
            'departure.name','departure','from.city.name','from.city','from.name','from',
            'start.city.name','start.city','start.name','start','pickup.city.name','pickup.city',
            'pickup.name','pickup','job.source.city','job.origin.city','job.departure.city',
            'route.from.city','route.origin.city','route.start.city','route.source.city',
            'route.departure.city','route.from','route.origin','route.start','route.source',
            'locations.source.city','locations.origin.city','cities.from.name','cities.origin.name'
        ))
        destination=find_city(j, (
            'destination_city.name','destinationCity.name','destination.city.name','destination.name',
            'destination_city','destinationCity','to_city.name','toCity.name','to_city','delivery_city.name',
            'deliveryCity.name','destination.city','destination','delivery.city.name','delivery.city',
            'delivery.name','delivery','to.city.name','to.city','to.name','to',
            'end.city.name','end.city','end.name','end','dropoff.city.name','dropoff.city',
            'dropoff.name','dropoff','job.destination.city','job.delivery.city',
            'route.to.city','route.destination.city','route.end.city','route.delivery.city',
            'route.arrival.city','route.to','route.destination','route.end','route.delivery',
            'locations.destination.city','cities.to.name','cities.destination.name'
        ))
        def label(v):
            if isinstance(v,dict):v=pick(v,'name','title','label')
            return str(v)[:120] if isinstance(v,(str,int,float)) else ''
        out.append({'driver':str(driver),'km':round(km,2),'date':date[:10],'vehicle_type':vehicle_type(j),'cargo':label(cargo),'origin':label(origin),'destination':label(destination)})
    return {'jobs':out,'ignored':ignored,'total_received':len(jobs)}

# Import local des exports Trucky au format XLSX (bibliotheque standard Python uniquement).
def load_export(path):
    import zipfile, xml.etree.ElementTree as ET, datetime
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            strings=[''.join(n.text or '' for n in si.findall('.//m:t',ns)) for si in root.findall('m:si',ns)]
        root=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        rows=[]
        for row in root.findall('.//m:sheetData/m:row',ns):
            cells={}
            for c in row.findall('m:c',ns):
                ref=c.attrib.get('r',''); letters=''.join(x for x in ref if x.isalpha());idx=0
                for letter in letters:idx=idx*26+ord(letter.upper())-64
                v=c.find('m:v',ns)
                inline=c.find('m:is',ns)
                if v is not None:
                    value=v.text or ''
                    if c.attrib.get('t')=='s':value=strings[int(value)]
                elif inline is not None:value=''.join(x.text or '' for x in inline.findall('.//m:t',ns))
                else:value=''
                cells[idx-1]=value
            if cells:rows.append([cells.get(i,'') for i in range(max(cells)+1)])
    if not rows:raise ValueError('Export Excel vide')
    headers={str(h).strip().lower():i for i,h in enumerate(rows[0])}
    needed=['driver','cargo','distance (km)','last update']
    if any(k not in headers for k in needed):raise ValueError('Colonnes Trucky manquantes dans jobs.xlsx')
    def get(row,key):
        i=headers[key];return row[i] if i<len(row) else ''
    jobs=[];ignored=0
    for row in rows[1:]:
        if 'status' in headers and str(get(row,'status')).lower()!='completed':continue
        try:
            km=float(str(get(row,'distance (km)')).replace(',','.'))
            if not 0<=km<=100000:raise ValueError()
            driver=str(get(row,'driver')).strip()
            if not driver:raise ValueError()
            stamp=float(get(row,'last update'))
            date=(datetime.datetime(1899,12,30)+datetime.timedelta(days=stamp)).date().isoformat()
        except (ValueError,TypeError,OverflowError):ignored+=1;continue
        cargo=str(get(row,'cargo')).casefold()
        vehicle='bus' if 'passager' in cargo or 'passenger' in cargo else ('camion' if cargo.strip() else 'inconnu')
        jobs.append({'driver':driver,'km':round(km,2),'date':date,'vehicle_type':vehicle,'cargo':str(get(row,'cargo')),'origin':'','destination':''})
    return {'jobs':jobs,'ignored':ignored,'total_received':len(rows)-1,'source':'export XLSX local (mise a jour manuelle)'}

# Synchronisation directe de l'API Trucky, sans Excel.
# Pagination adaptee aux metadonnees renvoyees par l'API.
import urllib.parse, time, threading
CACHE = {'data': None, 'time': 0}
LOCK = threading.Lock()

def extract_jobs(payload):
    if isinstance(payload, list): return payload
    if isinstance(payload, dict):
        for obj in (payload, payload.get('data')):
            if isinstance(obj, dict):
                for k in ('jobs', 'items', 'results', 'data'):
                    if isinstance(obj.get(k), list): return obj[k]
    raise ValueError('Structure des livraisons Trucky inconnue')

def pagination_info(payload):
    if not isinstance(payload, dict): return {}
    for obj in (payload, payload.get('pagination'), payload.get('meta'), payload.get('data')):
        if isinstance(obj, dict):
            for key in ('next_page_url', 'nextPageUrl', 'next', 'next_page', 'nextPage', 'next_cursor', 'nextCursor', 'total_pages', 'totalPages', 'last_page', 'lastPage'):
                if obj.get(key) is not None: return obj
    return {}

def fetch_all(token):
    base='https://e.truckyapp.com/api/v1/company/22154/jobs'
    headers={'x-access-token':token,'Accept':'application/json','Content-Type':'application/json','User-Agent':'RPTPFR-DriversDashboard/2.0'}
    jobs=[];seen=set();url=base;page=1;pagination_detected=False;warning=None
    for _ in range(150):
        req=urllib.request.Request(url,headers=headers)
        with urllib.request.urlopen(req,timeout=25) as response: payload=json.load(response)
        batch=extract_jobs(payload)
        if not batch:break
        new=0
        for j in batch:
            if not isinstance(j,dict):continue
            key=str(pick(j,'id','job_id','jobId','uuid') or json.dumps(j,sort_keys=True,ensure_ascii=False))
            if key not in seen:seen.add(key);jobs.append(j);new+=1
        if not new:break
        meta=pagination_info(payload)
        next_url=pick(meta,'next_page_url','nextPageUrl','next')
        cursor=pick(meta,'next_cursor','nextCursor')
        next_page=pick(meta,'next_page','nextPage')
        total_pages=pick(meta,'total_pages','totalPages','last_page','lastPage')
        if isinstance(next_url,str) and next_url.startswith(('https://e.truckyapp.com/','/api/')):
            url=urllib.parse.urljoin(base,next_url);pagination_detected=True
        elif cursor:
            url=base+'?'+urllib.parse.urlencode({'cursor':cursor});pagination_detected=True
        elif next_page and str(next_page).isdigit():
            page=int(next_page);url=base+'?'+urllib.parse.urlencode({'page':page});pagination_detected=True
        elif total_pages and str(total_pages).isdigit() and page<int(total_pages):
            page+=1;url=base+'?'+urllib.parse.urlencode({'page':page});pagination_detected=True
        elif not meta and len(batch)>=20:
            # Essai prudent : certaines API ne fournissent aucune metadonnee.
            # L'absence de nouveaux identifiants arrete immediatement la collecte.
            page+=1;url=base+'?'+urllib.parse.urlencode({'page':page})
        else:break
    if len(jobs)<=20:
        warning='L’API ne fournit que %s trajets. L’historique complet n’est pas garanti ; les paramètres de pagination doivent être confirmés auprès de Trucky.' % len(jobs)
    result=normalize(jobs)
    result.update(source='API Trucky directe',pages_checked=page,warning=warning)
    return result

class Handler(http.server.BaseHTTPRequestHandler):
    def reply(self,status,data):
        body=json.dumps(data,ensure_ascii=False).encode('utf-8');self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def json_response(self,status,data,cookie=None):
        body=json.dumps(data,ensure_ascii=False,default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if cookie:self.send_header('Set-Cookie',cookie)
        self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)
    def do_POST(self):self.mutate('POST')
    def do_PUT(self):self.mutate('PUT')
    def do_DELETE(self):self.mutate('DELETE')
    def mutate(self,method):
        import re
        path=self.path.split('?')[0]
        if not path.startswith('/api/admin/') or not challenges.check_origin(self):return self.json_response(403,{'error':'Requête interdite (origine invalide)'})
        try:
            data=challenges.read_json(self)
            if path=='/api/admin/login' and method=='POST':
                if not challenges.password_ok(str(data.get('password',''))):return self.json_response(401,{'error':'Mot de passe incorrect'})
                return self.json_response(200,{'ok':True},challenges.cookie_header(challenges.make_cookie()))
            if not challenges.logged_in(self):return self.json_response(401,{'error':'Session expirée : reconnecte-toi'})
            if path=='/api/admin/logout' and method=='POST':return self.json_response(200,{'ok':True},challenges.cookie_header('',0))
            if path=='/api/admin/discord-daily-test' and method=='POST':
                # Envoi manuel du vrai rapport, sans consommer l'envoi automatique de midi.
                try:
                    import daily_discord
                    sent = daily_discord.main(force=True)
                    if not sent:
                        return self.json_response(409,{'error':'Rapport en cours de préparation : réessaie dans quelques instants.'})
                    return self.json_response(200,{'ok':True,'message':'Classements BUS/CAMION de la veille transmis à Discord. L’envoi automatique de midi reste actif.'})
                except urllib.error.HTTPError as exc:
                    print('[TEST CLASSEMENT DISCORD] HTTP', exc.code, flush=True)
                    return self.json_response(502,{'error':'Discord ou Trucky a répondu HTTP '+str(exc.code)})
                except Exception as exc:
                    print('[TEST CLASSEMENT DISCORD] Échec :', repr(exc), flush=True)
                    return self.json_response(503,{'error':'Envoi impossible. Consulte les logs Render pour connaître la cause.'})
            if path=='/api/admin/discord-message' and method=='POST':
                message=data.get('message','')
                ping=data.get('ping',False)
                if not isinstance(message,str) or not (1 <= len(message.strip()) <= 1500):
                    return self.json_response(400,{'error':'Message requis (1 à 1500 caractères).'})
                if not isinstance(ping,bool):
                    return self.json_response(400,{'error':'Option de mention invalide.'})
                webhook=os.environ.get('DISCORD_WEBHOOK_URL','').strip()
                if not webhook.startswith(('https://discord.com/api/webhooks/','https://discordapp.com/api/webhooks/')):
                    return self.json_response(503,{'error':'DISCORD_WEBHOOK_URL absent du Web Service Render.'})
                # Mention volontaire uniquement ; toute autre mention est neutralisée.
                safe=message.strip().replace('@','@\u200b')
                content=('@everyone\n' if ping else '')+safe
                payload={'username':'ЯPTPFR • Service Administration Entreprise','content':content,
                         'allowed_mentions':{'parse':['everyone'] if ping else []}}
                req=urllib.request.Request(webhook,data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
                    headers={'Content-Type':'application/json','User-Agent':'RPTPFR-Admin/1.0'},method='POST')
                try:
                    with urllib.request.urlopen(req,timeout=15) as response:
                        if response.status not in (200,204):
                            return self.json_response(502,{'error':'Discord a répondu HTTP '+str(response.status)})
                except urllib.error.HTTPError as exc:
                    return self.json_response(502,{'error':'Discord a répondu HTTP '+str(exc.code)})
                except (urllib.error.URLError,TimeoutError):
                    return self.json_response(502,{'error':'Connexion à Discord impossible.'})
                return self.json_response(200,{'ok':True,'message':'Message transmis à Discord.'})
            match=re.fullmatch(r'/api/admin/challenges(?:/(\d+))?',path)
            if not match:return self.json_response(404,{'error':'Route introuvable'})
            ident=int(match.group(1)) if match.group(1) else None
            if method=='POST' and ident is None:
                values=challenges.validate(data)
                with challenges.db() as conn:conn.execute('INSERT INTO challenges(title,description,transport,mode,target_km,start_date,end_date,active,discord_webhook) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',values)
                # L'enregistrement reste valide même si Discord est temporairement indisponible.
                sent, discord_message = challenges.announce_creation(values)
                return self.json_response(200, {'ok':True,'discord_sent':sent,'discord_message':discord_message})
            elif method=='PUT' and ident is not None:
                values=challenges.validate(data)
                with challenges.db() as conn:
                    cur=conn.execute('UPDATE challenges SET title=%s,description=%s,transport=%s,mode=%s,target_km=%s,start_date=%s,end_date=%s,active=%s,discord_webhook=%s WHERE id=%s',(*values,ident))
                    if cur.rowcount==0:return self.json_response(404,{'error':'Challenge introuvable'})
            elif method=='DELETE' and ident is not None:
                with challenges.db() as conn:conn.execute('DELETE FROM challenges WHERE id=%s',(ident,))
            else:return self.json_response(405,{'error':'Méthode non autorisée'})
            return self.json_response(200,{'ok':True})
        except (ValueError,KeyError,TypeError,OverflowError) as e:return self.json_response(400,{'error':str(e)})
        except Exception:return self.json_response(503,{'error':'Base de données ou configuration indisponible'})
    def do_GET(self):
        path=self.path.split('?')[0]
        if path in ('/api/scs/news', '/api/scs-news'):
            try:
                return self.json_response(200,{'news':scs_news.fetch_news(10)})
            except urllib.error.HTTPError as exc:
                print(f'SCS NEWS: Steam HTTP {exc.code}', flush=True)
                return self.json_response(502,{'error':f'Steam a répondu HTTP {exc.code}'})
            except Exception as exc:
                print(f'SCS NEWS: {type(exc).__name__}: {exc}', flush=True)
                return self.json_response(502,{'error':'Actualités ETS2 indisponibles : consulter les logs Render (SCS NEWS)'})
        if path=='/api/truckersmp/servers':
            try:
                request=urllib.request.Request('https://api.truckersmp.com/v2/servers',headers={'Accept':'application/json','User-Agent':'RPTPFR-Dashboard/1.0'})
                with urllib.request.urlopen(request,timeout=12) as response:
                    payload=json.load(response)
                raw=payload.get('response',[]) if isinstance(payload,dict) else []
                if not isinstance(raw,list):raise ValueError('Réponse TruckersMP inattendue')
                servers=[]
                for entry in raw:
                    if not isinstance(entry,dict):continue
                    game=str(entry.get('game','')).lower()
                    if game and game not in ('ets2','eurotrucksimulator2','euro truck simulator 2'):continue
                    servers.append({'name':str(entry.get('name','Serveur')),'online':bool(entry.get('online',False)),'players':int(entry.get('players') or 0),'maxplayers':int(entry.get('maxplayers') or 0),'queue':int(entry.get('queue') or 0)})
                return self.json_response(200,{'servers':servers})
            except Exception:
                return self.json_response(502,{'error':'API TruckersMP indisponible temporairement'})
        if path=='/admin':
            body=challenges.ADMIN_HTML.encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'");self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        if path=='/api/admin/trucky-fields':
            if not challenges.logged_in(self):
                return self.json_response(401, {'error':'Connexion administrateur nécessaire (/admin)'})
            try:
                token=os.environ.get('TRUCKY_TOKEN','').strip()
                if not token:
                    return self.json_response(503, {'error':'TRUCKY_TOKEN manquant'})
                request=urllib.request.Request('https://e.truckyapp.com/api/v1/company/22154/jobs',headers={
                    'x-access-token':token,'Accept':'application/json','User-Agent':'RPTPFR-DriversDashboard/2.0'})
                with urllib.request.urlopen(request,timeout=25) as response:
                    payload=json.load(response)
                jobs=extract_jobs(payload)
                def field_paths(obj,prefix='',depth=0):
                    if depth>=5 or not isinstance(obj,dict):return []
                    result=[]
                    for key,value in obj.items():
                        path=(prefix+'.' if prefix else '')+str(key)
                        result.append(path+'[]' if isinstance(value,list) else path)
                        if isinstance(value,dict):result.extend(field_paths(value,path,depth+1))
                    return result[:300]
                return self.json_response(200,{
                    'message':'Uniquement les noms des champs Trucky, aucune valeur privée ni token.',
                    'missions_recues':len(jobs),
                    'champs_premiere_mission':field_paths(jobs[0]) if jobs else [],
                    'champs_reponse':list(payload.keys()) if isinstance(payload,dict) else []
                })
            except Exception as exc:
                print('TRUCKY FIELDS:',type(exc).__name__,str(exc),flush=True)
                return self.json_response(502,{'error':'Diagnostic Trucky indisponible, consulter les logs Render'})
        if path=='/api/admin/challenges':
            if not challenges.logged_in(self):return self.json_response(401,{'error':'Connexion nécessaire'})
            try:return self.json_response(200,{'challenges':challenges.list_challenges()})
            except Exception:return self.json_response(503,{'error':'Base de données indisponible'})
        if path=='/api/challenges':
            try:
                token=os.environ.get('TRUCKY_TOKEN','').strip()
                if not token:return self.json_response(503,{'error':'TRUCKY_TOKEN manquant'})
                with LOCK:
                    if CACHE['data'] is None or time.time()-CACHE['time']>300:
                        CACHE['data']=fetch_all(token);CACHE['time']=time.time()
                    jobs=CACHE['data']['jobs']
                return self.json_response(200,{'challenges':challenges.public_challenges(jobs)})
            except Exception:return self.json_response(503,{'error':'Challenges indisponibles : vérifier la base et Trucky'})

        if self.path=='/':
            html=(ROOT/'index.html').read_bytes()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(html)));self.end_headers();self.wfile.write(html);return
        if self.path in ('/logo-rptpfr.png','/banniere-rptpfr.png'):
            asset=ROOT/self.path.lstrip('/')
            body=asset.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type','image/png')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','public, max-age=3600')
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path=='/health':return self.reply(200,{'status':'ok'})
        if self.path!='/api/jobs':return self.reply(404,{'error':'Page introuvable'})
        try:
            token=os.environ.get('TRUCKY_TOKEN','').strip()
            if not token and CONFIG.exists():
                config=json.loads(CONFIG.read_text(encoding='utf-8'))
                token=config.get('trucky_token','').strip()
            if not token or token.startswith('COLLER_'):return self.reply(503,{'error':'Configure TRUCKY_TOKEN dans Render > Environment.'})
            with LOCK:
                if CACHE['data'] is None or time.time()-CACHE['time']>300:
                    CACHE['data']=fetch_all(token);CACHE['time']=time.time()
                data=CACHE['data']
            self.reply(200,data)
        except urllib.error.HTTPError as e:self.reply(502,{'error':f'Trucky a répondu HTTP {e.code}. Vérifie le token et les autorisations.'})
        except Exception as e:self.reply(502,{'error':str(e)})

def start_daily_discord_scheduler():
    """Programmation intégrée, sans Cron Job, à partir de 12 h heure de Paris."""
    import threading
    from zoneinfo import ZoneInfo
    paris = ZoneInfo('Europe/Paris')

    def worker():
        import daily_discord
        last_attempt = None
        while True:
            try:
                now = datetime.datetime.now(paris)
                # Vérification chaque minute ; une relance après midi rattrape le rapport.
                # Limite les tentatives à une par tranche de 15 minutes.
                attempt = (now.date(), now.hour, now.minute // 15)
                if now.hour >= 12 and attempt != last_attempt:
                    last_attempt = attempt
                    daily_discord.main()
            except Exception as exc:
                print('[DISCORD QUOTIDIEN] Échec :', repr(exc), flush=True)
            time.sleep(60)

    threading.Thread(target=worker, name='rptpfr-discord-daily', daemon=True).start()
    print('[DISCORD QUOTIDIEN] Programmateur interne démarré (Europe/Paris, 12 h).', flush=True)

if __name__=='__main__':
    from http.server import ThreadingHTTPServer
    port=int(os.environ.get('PORT','8765'))
    host='0.0.0.0' if os.environ.get('RENDER') else '127.0.0.1'
    challenges.setup()
    start_daily_discord_scheduler()
    with ThreadingHTTPServer((host,port),Handler) as server:
        print(f'RPTPFR sur {host}:{port}',flush=True)
        server.serve_forever()
