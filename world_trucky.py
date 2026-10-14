"""Lecture prudente des classements Trucky ETS2.

Une seule catégorie par passage, un seul Chromium à la fois. Les résultats
valides ne sont jamais remplacés par une réponse vide ou une erreur.
"""
import datetime as dt
import json
import os
import re
import threading
import time
from pathlib import Path

START_URL = 'https://hub.truckyapp.com/leaderboards/companies/distance'
MODES = ['Total', 'Distance (Réel)', 'Distance (Course)', 'WOTR', 'TruckersMP', 'Transport public']
INTERVAL = int(os.environ.get('TRUCKY_WORLD_INTERVAL', '180'))
CACHE_FILE = Path(os.environ.get('TRUCKY_WORLD_CACHE_FILE', '/tmp/rptpfr_world_rankings.json'))
LOCK = threading.Lock()
STATE = {'status': 'idle', 'updated_at': None, 'categories': [
    {'name': name, 'url': START_URL, 'top10': [], 'rptpfr': None,
     'loaded_rows': 0, 'verified': False} for name in MODES], 'error': None}
NEXT_ATTEMPT = 0.0
NEXT_INDEX = 0
RUNNING = False

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
    result.push({rank, name, distance: clean(km[0]), text});
  }
  return result.sort((a,b) => a.rank - b.rank);
}"""


def _select_mode(page, mode):
    # Le menu Trucky est un sélecteur JavaScript, pas un <select> HTML.
    trigger = page.get_by_role('button', name=re.compile(
        r'Total|Distance|WOTR|TruckersMP|Transport public', re.I))
    if trigger.count():
        trigger.first.click(timeout=3500)
    else:
        page.get_by_text('Transport public', exact=True).first.click(timeout=3500)
    page.get_by_text(mode, exact=True).last.click(timeout=5000)
    page.get_by_text('Rechercher', exact=True).first.click(timeout=5000)
    page.wait_for_timeout(1500)


def _read_one(mode):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,
                                     args=['--no-sandbox', '--disable-dev-shm-usage'])
        try:
            page = browser.new_page(viewport={'width': 1600, 'height': 1100}, locale='fr-FR')
            page.set_default_timeout(5000)
            page.goto(START_URL, wait_until='domcontentloaded', timeout=20000)
            page.wait_for_timeout(1600)
            _select_mode(page, mode)
            cards = page.evaluate(CARD_JS)
            # Le rang est déjà fourni par le HTML de la page d'accueil.
            top = [f"{c['name']} — {c['distance']}" for c in cards if c['rank'] <= 10][:10]
            own = next((c for c in cards if 'RPTPFR' in c['name'].upper()
                        or 'ЯPTPFR' in c['name'].upper()), None)
            return {'name': mode, 'url': START_URL, 'top10': top,
                    'rptpfr': f"{own['rank']}. {own['name']} — {own['distance']}" if own else None,
                    'loaded_rows': len(cards), 'verified': bool(top)}
        finally:
            browser.close()


def _save_cache():
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = CACHE_FILE.with_suffix('.tmp')
        temp.write_text(json.dumps({'categories': STATE['categories'],
                                    'updated_at': STATE['updated_at']}, ensure_ascii=False), encoding='utf-8')
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
        STATE['updated_at'] = saved.get('updated_at')
        if known:
            STATE['status'] = 'ready'
    except (OSError, ValueError, KeyError, TypeError):
        pass


def _worker(index):
    global RUNNING
    mode = MODES[index]
    try:
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


def snapshot():
    global RUNNING, NEXT_ATTEMPT, NEXT_INDEX
    with LOCK:
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
        return json.loads(json.dumps(STATE, ensure_ascii=False))


_restore_cache()
