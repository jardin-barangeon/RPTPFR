"""Classements publics Trucky ETS2 (mois courant), lecture best-effort.
Aucun rang n'est inventé : seules les cartes effectivement lues sont publiées.
"""
import datetime as dt
import re
import threading
import time

START_URL = 'https://hub.truckyapp.com/leaderboards/companies/distance'
MODES = ['Total', 'Distance (Réel)', 'Distance (Course)', 'WOTR', 'TruckersMP', 'Transport public']
LOCK = threading.Lock()
STATE = {'status': 'idle', 'updated_at': None, 'categories': [], 'error': None}
LAST_ATTEMPT = 0

# Trucky affiche des cartes, et non des lignes <table>. On cherche les cartes
# qui possèdent un kilométrage, un nom et un numéro de classement visibles.
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
    """Sélectionne explicitement le filtre de transport, puis lance la recherche."""
    # Trucky utilise un menu personnalisé. On ouvre le menu via son libellé
    # courant, sans cliquer sur les noms des entreprises dans les cartes.
    choices = page.get_by_text(mode, exact=True)
    if mode == 'Transport public':
        # Au premier affichage, le filtre est souvent déjà sur Transport public.
        trigger = page.get_by_text('Transport public', exact=True).first
    else:
        trigger = page.get_by_text('Transport public', exact=True).first
    try:
        # Les filtres sont regroupés au-dessus du bouton Rechercher.
        # Le bouton du menu est souvent le seul affichant le mode actif.
        candidate = page.locator('button').filter(has_text=re.compile(r'^(Total|Distance \(Réel\)|Distance \(Course\)|WOTR|TruckersMP|Transport public)\s*[⌄▾▼]?$'))
        if candidate.count():
            candidate.first.click(timeout=4000)
        else:
            trigger.click(timeout=4000)
        page.get_by_text(mode, exact=True).last.click(timeout=4000)
    except Exception:
        # Si le mode demandé est déjà sélectionné, le bouton Rechercher suffit.
        if not page.get_by_text(mode, exact=True).count():
            raise
    page.get_by_text('Rechercher', exact=True).first.click(timeout=6000)
    page.wait_for_timeout(2500)


def _read():
    from playwright.sync_api import sync_playwright
    categories = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        try:
            page = browser.new_page(viewport={'width': 1600, 'height': 1100}, locale='fr-FR')
            page.goto(START_URL, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(3500)
            for mode in MODES:
                entry = {'name': mode, 'url': START_URL, 'top10': [], 'rptpfr': None,
                         'loaded_rows': 0, 'verified': False}
                try:
                    _select_mode(page, mode)
                    cards = page.evaluate(CARD_JS)
                    # Le TOP 10 provient de la première page. Ne jamais attribuer
                    # une position à partir du numéro d'une ligne locale.
                    first_page = list(cards)
                    entry['top10'] = [f"{c['name']} — {c['distance']}" for c in first_page if c['rank'] <= 10][:10]
                    entry['verified'] = bool(entry['top10'])
                    entry['loaded_rows'] = len(cards)
                    own = next((c for c in cards if 'RPTPFR' in c['name'].upper() or 'ЯPTPFR' in c['name'].upper()), None)
                    # Parcours limité des pages pour chercher notre entreprise.
                    # Ne pas annoncer un rang si la pagination n'est pas fiable.
                    for page_number in range(2, 6):
                        if own or not entry['verified']:
                            break
                        # Les boutons de pagination affichent le numéro de page.
                        next_page = page.get_by_role('button', name=str(page_number), exact=True)
                        if not next_page.count():
                            break
                        try:
                            next_page.last.click(timeout=2500)
                            page.wait_for_timeout(1100)
                            more = page.evaluate(CARD_JS)
                        except Exception:
                            break
                        if not more or [(c['name'], c['distance']) for c in more] == [(c['name'], c['distance']) for c in cards]:
                            break
                        cards = more
                        entry['loaded_rows'] += len(more)
                        own = next((c for c in more if 'RPTPFR' in c['name'].upper() or 'ЯPTPFR' in c['name'].upper()), None)
                    if own:
                        entry['rptpfr'] = f"{own['rank']}. {own['name']} — {own['distance']}"
                    if not entry['verified']:
                        entry['error'] = 'Aucune carte de classement identifiable après sélection du filtre'
                except Exception as exc:
                    entry['error'] = f'{type(exc).__name__}: {str(exc)[:180]}'
                categories.append(entry)
                # Revenir à une page neuve pour éviter les effets de pagination
                # entre deux modes différents.
                if mode != MODES[-1]:
                    page.goto(START_URL, wait_until='domcontentloaded', timeout=30000)
                    page.wait_for_timeout(1800)
        finally:
            browser.close()
    return categories


def _worker():
    try:
        categories = _read()
        with LOCK:
            STATE.update(status='ready', categories=categories,
                         updated_at=dt.datetime.now(dt.timezone.utc).isoformat(), error=None)
    except Exception as exc:
        with LOCK:
            STATE.update(status='error', error=f'{type(exc).__name__}: {str(exc)[:220]}',
                         updated_at=dt.datetime.now(dt.timezone.utc).isoformat())
        print('[TRUCKY MONDIAL]', repr(exc), flush=True)


def snapshot():
    global LAST_ATTEMPT
    with LOCK:
        if STATE['status'] != 'loading' and time.time() - LAST_ATTEMPT > 3600:
            LAST_ATTEMPT = time.time()
            STATE['status'] = 'loading'
            threading.Thread(target=_worker, daemon=True, name='trucky-world').start()
        return dict(STATE)
