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
    result.push({rank, name, distance: clean(km[0]), text});
  }
  return result.sort((a,b) => a.rank - b.rank);
}"""


def _select_mode(page, mode):
    """Choisit Truck Mode dans le menu personnalisé, sans bouton Rechercher."""
    # Les libellés sont des éléments du menu, pas nécessairement des boutons.
    # Déterminer le déclencheur par sa proximité avec « Truck Mode ».
    details = page.evaluate(r"""(target) => {
      const modes = ['Total','Distance (Réel)','Distance (Course)','WOTR','TruckersMP','Transport public'];
      const clean = x => (x || '').replace(/\s+/g,' ').trim();
      const visible = e => !!e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
      const leaf = [...document.querySelectorAll('body *')].filter(e => visible(e) &&
        e.children.length === 0 && modes.includes(clean(e.textContent)));
      const labelled = [...document.querySelectorAll('body *')].find(e => visible(e) &&
        e.children.length === 0 && clean(e.textContent) === 'Truck Mode');
      const choices = leaf.filter(e => {
        const clickable = e.closest('button,[role="button"],[role="combobox"],[aria-haspopup]');
        return !!clickable;
      });
      const near = labelled && labelled.parentElement && labelled.parentElement.parentElement;
      let trigger = near && [...near.querySelectorAll('button,[role="button"],[role="combobox"],[aria-haspopup]')]
        .find(e => modes.includes(clean(e.innerText || e.textContent)));
      if (!trigger) trigger = choices.map(e => e.closest('button,[role="button"],[role="combobox"],[aria-haspopup]'))
        .find(e => modes.includes(clean(e.innerText || e.textContent)) &&
          (e.getAttribute('aria-haspopup') || e.getAttribute('role') === 'combobox'));
      if (!trigger) trigger = choices.map(e => e.closest('button,[role="button"],[role="combobox"],[aria-haspopup]'))[0];
      if (!trigger) return {ok:false,reason:'Déclencheur Truck Mode introuvable'};
      const current = clean(trigger.innerText || trigger.textContent);
      if (current !== target) trigger.click();
      return {ok:true,already:current === target,current};
    }""", mode)
    if not details.get('ok'):
        raise RuntimeError(details.get('reason', 'Truck Mode inaccessible'))
    if not details.get('already'):
        page.wait_for_timeout(300)
        selected = page.evaluate(r"""(target) => {
          const clean = x => (x || '').replace(/\s+/g,' ').trim();
          const visible = e => !!e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
          const nodes = [...document.querySelectorAll('body *')].filter(e => visible(e) &&
            e.children.length === 0 && clean(e.textContent) === target);
          const option = nodes.map(e => e.closest('[role="option"],[role="menuitem"],li,button,a') || e)
            .find(e => visible(e));
          if (!option) return false;
          option.click();
          return true;
        }""", mode)
        if not selected:
            raise RuntimeError(f'Option Truck Mode introuvable : {mode}')
    # Attendre que le libellé du mode soit celui du sélecteur fermé. Ne pas
    # attribuer le tableau de la catégorie précédente au nouveau mode.
    try:
        page.wait_for_function(r"""(target) => {
          const clean = x => (x || '').replace(/\s+/g,' ').trim();
          const visible = e => !!e.getClientRects().length;
          const modes = ['Total','Distance (Réel)','Distance (Course)','WOTR','TruckersMP','Transport public'];
          const label = [...document.querySelectorAll('body *')].find(e =>
            visible(e) && e.children.length === 0 && clean(e.textContent) === 'Truck Mode');
          if (!label) return false;
          const near = label.parentElement && label.parentElement.parentElement;
          return !!near && [...near.querySelectorAll('button,[role="button"],[role="combobox"],[aria-haspopup]')]
            .some(e => visible(e) && clean(e.innerText || e.textContent) === target);
        }""", mode, timeout=6000)
    except Exception as exc:
        raise RuntimeError(f'Sélection de {mode} non confirmée : {str(exc)[:90]}') from exc
    page.wait_for_timeout(1800)


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
            cards = []
            for _ in range(8):
                cards = page.evaluate(CARD_JS)
                if cards:
                    break
                page.wait_for_timeout(700)
            if not cards:
                print('[TRUCKY MONDIAL]', mode,
                      'aucune carte détectée ; URL:', page.url,
                      'titre:', page.title(), flush=True)
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
        return json.loads(json.dumps(STATE, ensure_ascii=False))


_restore_cache()
