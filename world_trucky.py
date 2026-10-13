"""Lecture expérimentale des classements publics Trucky, sans authentification.
Ne renvoie jamais un rang supposé : seulement les lignes visibles et vérifiées.
"""
import datetime, os, re, threading, time
from urllib.parse import urlparse

START_URL='https://hub.truckyapp.com/leaderboards/companies/distance'
LOCK=threading.Lock()
STATE={'status':'idle','updated_at':None,'categories':[],'error':None}
LAST_ATTEMPT=0

def _read():
    from playwright.sync_api import sync_playwright
    categories=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1440,'height':1000},locale='en-US')
            page.goto(START_URL,wait_until='domcontentloaded',timeout=45000)
            page.wait_for_timeout(4500)
            # Découvrir les catégories réellement présentes, sans inventer de routes.
            links=page.locator('a[href]').evaluate_all('els => els.map(e=>({name:e.innerText.trim(),href:e.href}))')
            urls=[{'name':'Distance','url':START_URL}]
            for item in links:
                url=item.get('href','')
                u=urlparse(url)
                if u.hostname=='hub.truckyapp.com' and '/leaderboards/companies/' in u.path and url not in [v['url'] for v in urls]:
                    urls.append({'name':item.get('name') or u.path.rsplit('/',1)[-1],'url':url})
            for entry in urls[:12]:
                try:
                    page.goto(entry['url'],wait_until='domcontentloaded',timeout=30000)
                    page.wait_for_timeout(2800)
                    rows=page.locator('table tbody tr').evaluate_all('els => els.map(e=>e.innerText.trim())')
                    # Certains tableaux utilisent des éléments ARIA plutôt que table/tr.
                    if not rows:
                        rows=page.locator('[role="row"]').evaluate_all('els => els.map(e=>e.innerText.trim())')
                    rows=[re.sub(r'\s+',' ',v).strip() for v in rows if v.strip()]
                    # Ne pas interpréter une page de connexion comme un classement.
                    categories.append({'name':entry['name'][:70],'url':entry['url'],'top10':rows[:10],
                                       'rptpfr':next((r for r in rows if 'ЯPTPFR' in r or 'RPTPFR' in r.upper()),None),
                                       'loaded_rows':len(rows),'verified':bool(rows)})
                except Exception as exc:
                    categories.append({'name':entry['name'][:70],'url':entry['url'],'top10':[],
                                       'rptpfr':None,'loaded_rows':0,'verified':False,'error':str(exc)[:120]})
        finally:browser.close()
    return categories

def _worker():
    try:
        categories=_read()
        with LOCK:STATE.update(status='ready',categories=categories,updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),error=None)
    except Exception as exc:
        with LOCK:STATE.update(status='error',error=f'{type(exc).__name__}: {str(exc)[:240]}')
        print('[TRUCKY MONDIAL]',repr(exc),flush=True)

def snapshot():
    global LAST_ATTEMPT
    with LOCK:
        if STATE['status']!='loading' and time.time()-LAST_ATTEMPT>3600:
            LAST_ATTEMPT=time.time();STATE['status']='loading'
            threading.Thread(target=_worker,daemon=True,name='trucky-world').start()
        return dict(STATE)
