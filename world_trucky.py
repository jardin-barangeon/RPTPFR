"""Lecture prudente des classements Trucky ETS2.

Une seule catégorie par passage, un seul Chromium à la fois. Les résultats
valides ne sont jamais remplacés par une réponse vide ou une erreur.
"""
import datetime as dt
import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse
import unicodedata
import threading
import time
from pathlib import Path

START_URL = 'https://hub.truckyapp.com/leaderboards/companies/distance'
MODES = ['Camion — Distance (Réel)', 'Coach — Distance (Réel)']
INTERVAL = int(os.environ.get('TRUCKY_WORLD_INTERVAL', '180'))
CACHE_FILE = Path(os.environ.get('TRUCKY_WORLD_CACHE_FILE', '/tmp/rptpfr_world_rankings.json'))
LOCK = threading.Lock()
STATE = {'status': 'idle', 'updated_at': None, 'categories': [
    {'name': name, 'url': START_URL, 'top10': [], 'rptpfr': None,
     'loaded_rows': 0, 'verified': False} for name in MODES], 'error': None}
NEXT_ATTEMPT = 0.0
NEXT_INDEX = 0
RUNNING = False
BACKGROUND_STARTED = False

CARD_JS = r"""() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const kmRE = /\b([\d\s.,]+)\s*km\b/i;
  const result = [], seen = new Set();
  const leaves = [...document.querySelectorAll('body *')].filter(e =>
    e.children.length === 0 && kmRE.test(clean(e.textContent)) &&
    clean(e.textContent).length < 65);
  for (const leaf of leaves) {
    let node = leaf, chosen = null;
    for (let i = 0; i < 7 && node; i++, node = node.parentElement) {
      const txt = clean(node.innerText);
      if (txt.length > 12 && txt.length < 260 && kmRE.test(txt) &&
          (node.querySelector('img') || /^\d{1,4}\b/.test(txt))) {
        chosen = node; break;
      }
    }
    if (!chosen) continue;
    const text = clean(chosen.innerText);
    const km = text.match(kmRE);
    if (!km) continue;
    const parts = chosen.innerText.split(/\n+/).map(clean).filter(Boolean);
    const rankPart = parts.find(s => /^\d{1,5}$/.test(s));
    const rank = rankPart ? Number(rankPart) : null;
    const name = parts.find(s => s !== rankPart && !kmRE.test(s) &&
       !/^(FR|US|CZ|DE|PL|RU|GB|ES|IT)$/i.test(s) && s.length > 2);
    if (!name || !rank || rank > 100000) continue;
    const key = `${rank}|${name}|${km[1]}`;
    if (seen.has(key)) continue;
    seen.add(key);
    // Chercher le conteneur visuel complet de cette entreprise, sans
    // remonter jusqu'au tableau qui contient plusieurs entreprises.
    let visual = chosen;
    for (let i = 0; i < 4 && visual.parentElement; i++) {
      const parent = visual.parentElement;
      const t = clean(parent.innerText);
      const matches = t.match(/\b[\d\s.,]+\s*km\b/gi) || [];
      if (matches.length > 1 || t.length > 350) break;
      visual = parent;
    }
    const imgs = [];
    const absolute = url => {
      try { const u = new URL(url, document.baseURI); return u.protocol === 'https:' ? u.href : null; }
      catch (_) { return null; }
    };
    for (const el of [visual, ...visual.querySelectorAll('img,[style],svg image')]) {
      let url = '';
      if (el.tagName === 'IMG') url = el.currentSrc || el.getAttribute('src') ||
        el.getAttribute('data-src') || el.getAttribute('data-original') || '';
      else if (el.tagName.toLowerCase() === 'image')
        url = el.getAttribute('href') || el.getAttribute('xlink:href') || '';
      if (!url) {
        const bg = getComputedStyle(el).backgroundImage;
        const m = bg && bg.match(/url\(["']?(.+?)["']?\)/);
        if (m) url = m[1];
      }
      url = absolute(url);
      if (url && !imgs.some(x => x.src === url))
        imgs.push({src:url, alt:(el.getAttribute('alt') || el.getAttribute('title') || el.getAttribute('class') || '').toString()});
    }
    const isFlag = x => /flag|country|\/flags?\/|flagcdn|\/w20\/|\/w40\//i.test(x.src+' '+x.alt) ||
      /^(?:[a-z]{2}|[a-z]{2}-[a-z]{2})$/i.test(x.alt.trim());
    const flag = imgs.find(isFlag);
    const logo = imgs.find(i => i !== flag && !/avatar-default|placeholder/i.test(i.src));
    result.push({rank, name, distance: clean(km[0]), text,
      logo_url: logo ? logo.src : null, flag_url: flag ? flag.src : null});
  }
  return result.sort((a,b) => a.rank - b.rank);
}"""


def _select_mode(page, mode):
    """Choisit explicitement Truck Mode ou Coaches > Distance (Réel).

    Ne considère jamais un libellé identique dans les deux groupes comme
    une confirmation suffisante : la sélection est faite par ordre de groupe.
    """
    group = 'Coaches' if mode.startswith('Coach') else 'Truck Mode'
    selected = page.evaluate(r"""(group) => {
      const clean = s => (s || '').replace(/\s+/g, ' ').trim();
      const visible = e => !!e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
      const all = [...document.querySelectorAll('body *')];
      const leaf = all.filter(e => e.children.length === 0 && visible(e));
      const trigger = leaf.filter(e => clean(e.textContent) === 'Distance (Réel)')
        .map(e => e.closest('button,[role="button"],[role="combobox"],[aria-haspopup]'))
        .find(e => e && visible(e) && !e.closest('[role="listbox"],[role="menu"]'));
      if (!trigger) return {ok:false,reason:'Sélecteur de distance introuvable'};
      trigger.click();
      return {ok:true};
    }""", group)
    if not selected.get('ok'):
        raise RuntimeError(selected.get('reason', 'Sélecteur Trucky inaccessible'))
    page.wait_for_timeout(350)
    result = page.evaluate(r"""(group) => {
      const clean = s => (s || '').replace(/\s+/g, ' ').trim();
      const visible = e => !!e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
      const all = [...document.querySelectorAll('body *')];
      const leaf = all.filter(e => e.children.length === 0 && visible(e));
      const headings = leaf.filter(e => clean(e.textContent) === 'Truck Mode' || clean(e.textContent) === 'Coaches');
      const options = leaf.filter(e => clean(e.textContent) === 'Distance (Réel)' && e.closest('[role=option],[role=menuitem],[role=listbox],[role=menu],li'));
      if (!headings.length || options.length < 2) return {ok:false,reason:'Menu Trucky Truck Mode / Coaches non reconnu'};
      const heading = headings.find(e => clean(e.textContent) === group);
      if (!heading) return {ok:false,reason:'Groupe '+group+' introuvable'};
      const pos = all.indexOf(heading);
      const next = headings.map(e => all.indexOf(e)).filter(i => i > pos).sort((a,b)=>a-b)[0] ?? Infinity;
      const choice = options.find(e => all.indexOf(e) > pos && all.indexOf(e) < next);
      if (!choice) return {ok:false,reason:'Distance (Réel) introuvable sous '+group};
      const clickable = choice.closest('[role="option"],[role="menuitem"],li,button,a') || choice;
      clickable.click();
      return {ok:true};
    }""", group)
    if not result.get('ok'):
        raise RuntimeError(result.get('reason', 'Catégorie Trucky non sélectionnée'))
    page.wait_for_timeout(1800)


def _name_key(name):
    plain = unicodedata.normalize('NFKD', str(name or '').casefold())
    return ''.join(c for c in plain if c.isalnum() and not unicodedata.combining(c))


def _image_directory():
    """Optional image metadata only; never use API distances to replace Coach results."""
    result = {}
    for category in ('real_miles', 'transport_system'):
        try:
            query = urllib.parse.urlencode({
                'country_code': '', 'game': 1, 'stats_type': category,
                'month': dt.datetime.now(dt.timezone.utc).month,
                'year': dt.datetime.now(dt.timezone.utc).year,
                'page': 1, 'perPage': 100})
            req = urllib.request.Request(
                'https://e.truckyapp.com/api/v1/companies/leaderboards?' + query,
                headers={'Accept':'application/json','User-Agent':'RPTPFR-World/1.0'})
            with urllib.request.urlopen(req, timeout=12) as response:
                payload = json.load(response)
            for item in payload.get('data', []):
                if not isinstance(item, dict): continue
                key = _name_key(item.get('name'))
                if not key: continue
                result[key] = {
                    'logo_url': item.get('avatar_url') or item.get('logo_url'),
                    'flag_url': item.get('flag_url')}
        except Exception as exc:
            print('[TRUCKY MONDIAL] Images API', category, type(exc).__name__, flush=True)
    return result


def _read_api(mode, france=False):
    """Classements officiels Trucky, sans navigateur ni sélection de menus."""
    category = 'coaches_real_miles' if 'Coach' in mode else 'real_miles'
    now = dt.datetime.now(dt.timezone.utc)
    params = urllib.parse.urlencode({
        'country_code': 'FR' if france else '',
        'game': 1, 'stats_type': category,
        'month': now.month, 'year': now.year,
        'page': 1, 'perPage': 18,
    })
    url = 'https://e.truckyapp.com/api/v1/companies/leaderboards?' + params
    request = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Origin': 'https://hub.truckyapp.com',
        'Referer': 'https://hub.truckyapp.com/',
        'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
    })
    try:
        with urllib.request.urlopen(request, timeout=22) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        print('[TRUCKY FRANCE]' if france else '[TRUCKY MONDIAL]',
              mode, 'HTTP', exc.code, 'Retry-After', exc.headers.get('Retry-After'), flush=True)
        raise
    # Les versions de l'API peuvent exposer les lignes sous data ou data.data.
    rows = payload.get('data') if isinstance(payload, dict) else None
    if isinstance(rows, dict):
        rows = rows.get('data') or rows.get('items') or rows.get('results')
    if not isinstance(rows, list):
        keys = list(payload)[:12] if isinstance(payload, dict) else type(payload).__name__
        raise ValueError(f'Format JSON Trucky inattendu : {keys}')
    cards = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        company = item.get('company') if isinstance(item.get('company'), dict) else {}
        name = str(item.get('name') or company.get('name') or '').strip()
        if not name:
            continue
        try:
            rank = int(item.get('position') or item.get('rank') or 0)
        except (ValueError, TypeError):
            continue
        if rank < 1:
            continue
        try:
            km = float(item.get('driven_distance') or item.get('distance') or item.get('value') or 0)
        except (ValueError, TypeError):
            continue
        distance = f"{km:,.0f}".replace(',', ' ') + ' ' + str(item.get('distance_unit') or 'km')
        logo = item.get('avatar_url') or item.get('logo_url') or company.get('avatar_url') or company.get('logo_url')
        flag = item.get('flag_url') or company.get('flag_url')
        cards.append({
            'rank': rank, 'name': name[:140], 'distance': distance,
            'logo_url': logo if isinstance(logo, str) and logo.startswith('https://') else None,
            'flag_url': flag if isinstance(flag, str) and flag.startswith('https://') else None,
            'company_id': item.get('company_id') or item.get('id'),
        })
    cards.sort(key=lambda x: x['rank'])
    top = cards[:10]
    if france:
        # L'API filtre les entreprises mais peut conserver les rangs mondiaux.
        # Afficher les rangs du Top France sans modifier les distances.
        top = [{**row, 'rank': i} for i, row in enumerate(top, start=1)]
    own = next((c for c in cards if 'RPTPFR' in c['name'].upper() or 'ЯPTPFR' in c['name'].upper()), None)
    print('[TRUCKY FRANCE]' if france else '[TRUCKY MONDIAL]',
          mode, 'API', category, 'lignes', len(cards), 'top', len(top),
          'exemple_champs', list(rows[0].keys())[:15] if rows and isinstance(rows[0], dict) else [], flush=True)
    return {
        'name': mode, 'url': START_URL, 'top10': top,
        'rptpfr': f"{own['rank']}. {own['name']} — {own['distance']}" if own else None,
        'loaded_rows': len(cards), 'verified': bool(top),
    }


def _read_one(mode):
    return _read_api(mode, france=False)


# Collecte française isolée : elle ne modifie JAMAIS les deux classements mondiaux.
FRANCE_MODES = ['France — Coach — Distance (Réel)', 'France — Camion — Distance (Réel)']
FRANCE_STATE = {name: {'name': name, 'url': START_URL, 'top10': [],
                      'rptpfr': None, 'loaded_rows': 0, 'verified': False}
                for name in FRANCE_MODES}
FRANCE_STARTED = False
FRANCE_RUNNING = False
FRANCE_NEXT = 0
FRANCE_ATTEMPT = 0.0
FRANCE_INTERVAL = max(120, int(os.environ.get('TRUCKY_FRANCE_INTERVAL', '480')))
FRANCE_SCRAPE_LOCK = threading.Lock()


def _select_france(page):
    """Sélectionne France dans le champ Pays et applique Rechercher.

    Si l'interface change, échoue sans afficher le classement mondial en France.
    """
    result = page.evaluate(r"""() => {
      const norm = s => (s||'').replace(/\s+/g,' ').trim().toLowerCase();
      const visible = e => !!e.getClientRects().length;
      const labels = [...document.querySelectorAll('body *')]
        .filter(e => e.children.length===0 && visible(e) && norm(e.textContent)==='pays');
      for(const label of labels){
        let p=label.parentElement;
        for(let i=0;i<5 && p;i++,p=p.parentElement){
          const fields=[...p.querySelectorAll('input,[role="combobox"],select')].filter(visible);
          if(fields.length===1){
            const field=fields[0];field.click();
            return {ok:true};
          }
        }
      }
      return {ok:false,reason:'champ Pays introuvable'};
    }""")
    if not result.get('ok'):
        raise RuntimeError(result.get('reason','Pays non sélectionnable'))
    page.wait_for_timeout(350)
    result = page.evaluate(r"""() => {
      const norm=s=>(s||'').replace(/\s+/g,' ').trim().toLowerCase();
      const visible=e=>!!e.getClientRects().length;
      const choices=[...document.querySelectorAll('[role="option"],li,button,[cmdk-item],select option')]
        .filter(e=>visible(e)&&norm(e.textContent)==='france');
      if(!choices.length)return {ok:false,reason:'option France absente'};
      const el=choices[choices.length-1];
      if(el.tagName==='OPTION'){
        const select=el.closest('select');select.value=el.value;
        select.dispatchEvent(new Event('change',{bubbles:true}));
      }else el.click();
      return {ok:true};
    }""")
    if not result.get('ok'):
        raise RuntimeError(result.get('reason','France non sélectionnable'))
    page.get_by_role('button',name='Rechercher',exact=True).click(timeout=5000)
    page.wait_for_timeout(2300)
    confirmed=page.evaluate(r"""() => {
      const norm=s=>(s||'').replace(/\s+/g,' ').trim().toLowerCase();
      const labels=[...document.querySelectorAll('body *')]
        .filter(e=>e.children.length===0&&norm(e.textContent)==='pays');
      return labels.some(label=>{
        let p=label.parentElement;
        for(let i=0;i<5&&p;i++,p=p.parentElement){
          const v=p.querySelector('input,[role="combobox"],select');
          if(v){
            const value=(v.value||v.textContent||v.getAttribute('aria-label')||'').toLowerCase();
            if(value.includes('france')||value==='fr')return true;
          }
          if(norm(p.innerText).includes('france')&&norm(p.innerText).length<150)return true;
        }
        return false;
      });
    }""")
    if not confirmed:
        raise RuntimeError('filtre France non confirmé après Rechercher')


def _read_france(mode):
    return _read_api(mode, france=True)


def _france_worker():
    global FRANCE_RUNNING, FRANCE_NEXT
    mode=FRANCE_MODES[FRANCE_NEXT]
    try:
        # Collecte France autonome, sans modifier les données mondiales.
        with FRANCE_SCRAPE_LOCK:
            result=_read_france(mode)
        if result['verified']:
            with LOCK:
                FRANCE_STATE[mode]=result
                _save_cache()
        else:
            print('[TRUCKY FRANCE]',mode,'aucun résultat, cache conservé',flush=True)
    except Exception as exc:
        print('[TRUCKY FRANCE]',mode,type(exc).__name__,str(exc)[:180],flush=True)
    finally:
        with LOCK:
            FRANCE_NEXT=(FRANCE_NEXT+1)%len(FRANCE_MODES)
            FRANCE_RUNNING=False


def _france_loop():
    global FRANCE_RUNNING, FRANCE_ATTEMPT
    while True:
        time.sleep(5)
        with LOCK:
            now=time.monotonic()
            # La collecte France est indépendante de la réussite des classements mondiaux.
            # Le verrou FRANCE_SCRAPE_LOCK évite toujours deux Chromium simultanés.
            if FRANCE_RUNNING or now<FRANCE_ATTEMPT:
                continue
            FRANCE_RUNNING=True
            FRANCE_ATTEMPT=now+FRANCE_INTERVAL
        threading.Thread(target=_france_worker,daemon=True,name='trucky-france-one').start()


def _save_cache():
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = CACHE_FILE.with_suffix('.tmp')
        temp.write_text(json.dumps({'categories': STATE['categories'],
                                    'updated_at': STATE['updated_at'], 'france': FRANCE_STATE}, ensure_ascii=False), encoding='utf-8')
        temp.replace(CACHE_FILE)
    except OSError as exc:
        print('[TRUCKY MONDIAL] Cache local non disponible:', str(exc), flush=True)


def _restore_cache():
    try:
        saved = json.loads(CACHE_FILE.read_text(encoding='utf-8'))
        known = {x['name']: x for x in saved.get('categories', []) if x.get('verified')}
        for i, cat in enumerate(STATE['categories']):
            if cat['name'] in known:
                STATE['categories'][i] = known[cat['name']]
        for name, result in saved.get('france', {}).items():
            if name in FRANCE_STATE and isinstance(result,dict) and result.get('verified'):
                FRANCE_STATE[name] = result
        STATE['updated_at'] = saved.get('updated_at')
        if known:
            STATE['status'] = 'ready'
    except (OSError, ValueError, KeyError, TypeError):
        pass


def _worker(index):
    global RUNNING
    mode = MODES[index]
    try:
        with FRANCE_SCRAPE_LOCK:
            result = _read_one(mode)
        with LOCK:
            if result['verified']:
                STATE['categories'][index] = result
                STATE['updated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
                STATE['error'] = None
                _save_cache()
            else:
                STATE['error'] = f'{mode} : aucune carte lisible, données précédentes conservées'
            STATE['status'] = 'ready'
    except Exception as exc:
        with LOCK:
            STATE['error'] = f'{mode} : {type(exc).__name__}: {str(exc)[:160]}'
            STATE['status'] = 'ready'
        print('[TRUCKY MONDIAL]', mode, repr(exc), flush=True)
    finally:
        with LOCK:
            RUNNING = False


def _background_loop():
    # Une visite suffit pour démarrer le cycle ; il continue sans autre requête HTTP.
    while True:
        time.sleep(15)
        try:
            snapshot()
        except Exception as exc:
            print('[TRUCKY MONDIAL] Planificateur:', repr(exc), flush=True)


def snapshot():
    global RUNNING, NEXT_ATTEMPT, NEXT_INDEX, BACKGROUND_STARTED
    with LOCK:
        if not BACKGROUND_STARTED:
            BACKGROUND_STARTED = True
            threading.Thread(target=_france_loop, daemon=True, name='trucky-france-scheduler').start()
            threading.Thread(target=_background_loop, daemon=True,
                             name='trucky-world-scheduler').start()
        now = time.monotonic()
        if not RUNNING and now >= NEXT_ATTEMPT:
            index = NEXT_INDEX
            NEXT_INDEX = (NEXT_INDEX + 1) % len(MODES)
            NEXT_ATTEMPT = now + max(90, INTERVAL)
            RUNNING = True
            STATE['status'] = 'loading' if not any(c['verified'] for c in STATE['categories']) else 'ready'
            threading.Thread(target=_worker, args=(index,), daemon=True,
                             name='trucky-world-one').start()
        # Copie isolée pour les réponses HTTP pendant la mise à jour du cache.
        response = dict(STATE)
        response['categories'] = STATE['categories'] + [FRANCE_STATE[n] for n in FRANCE_MODES]
        return json.loads(json.dumps(response, ensure_ascii=False))


_restore_cache()
