"""Synchronise les messages Discord avec les bouchons actifs ETS2 SIM1."""
import datetime
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import hashlib
import psycopg
from zoneinfo import ZoneInfo

TRAFFIC_URL = 'https://api.truckyapp.com/v2/traffic?game=ets2&server=sim1'
PARIS = ZoneInfo('Europe/Paris')
POLL_SECONDS = 120


def fetch_snapshot():
    req = urllib.request.Request(TRAFFIC_URL, headers={'Accept': 'application/json', 'User-Agent': 'RPTPFR-Traffic-Alerts/2.0'})
    with urllib.request.urlopen(req, timeout=18) as response:
        data = json.load(response)
    countries = data.get('response') if isinstance(data, dict) else None
    if not isinstance(countries, list):
        raise ValueError('Réponse Trucky invalide')
    result = {}
    cities = {}
    for group in countries:
        if not isinstance(group, dict):
            continue
        for loc in group.get('locations', []):
            if not isinstance(loc, dict):
                continue
            try:
                count = max(0, int(loc.get('trafficJams') or 0))
                players = max(0, int(loc.get('playersInvolvedInTrafficJams') or 0))
            except (ValueError, TypeError):
                continue
            country = str(group.get('country') or loc.get('country') or 'Pays inconnu')[:80]
            name = str(loc.get('name') or 'Zone inconnue')[:120]
            try:
                present = max(0, int(loc.get('players') or 0))
            except (ValueError, TypeError):
                present = 0
            if present >= 20 and name != 'Zone inconnue':
                city_key = (country.casefold(), name.casefold())
                # Une même localisation peut figurer dans plusieurs couches : ne pas compter deux fois.
                if city_key not in cities or present > cities[city_key]['players']:
                    cities[city_key] = {'country': country, 'name': name, 'players': present}
            if not count:
                continue
            key = str(loc.get('layerID') or (country + '|' + name))
            result[key] = {'country': country, 'name': name, 'count': count, 'players': players}
    return result, sorted(cities.values(), key=lambda c: (-c["players"], c["name"].casefold()))


def discord_request(url, method, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method,
        headers={'Content-Type': 'application/json', 'User-Agent': 'RPTPFR-Traffic-Alerts/2.0'})
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def payload(zone):
    now = datetime.datetime.now(PARIS)
    desc = ('**📍 Secteur :** {name}\n**🌍 Pays :** {country}\n'
            '**🚧 Embouteillage(s) :** {count}\n**🚗 Joueurs concernés :** {players}\n'
            '**🎮 Serveur :** ETS2 — Simulation 1\n**🕒 Actualisé à :** {hour} (Paris)').format(
                **zone, hour=now.strftime('%H:%M:%S'))
    return {'username': 'ЯPTPFR • Info Trafic', 'allowed_mentions': {'parse': []},
            'embeds': [{'title': '🚨 BOUCHON EN COURS', 'description': desc, 'color': 0xE34B4B,
                        'footer': {'text': 'Info trafic en direct • Source : Trucky • ЯPTPFR'},
                        'timestamp': now.isoformat()}]}



def cities_payload(cities):
    now = datetime.datetime.now(PARIS)
    # Limite Discord : 4096 caractères pour une description d'embed.
    lines = ['**Ville / secteur**  |  **Joueurs**  |  **Trafic**', '━━━━━━━━━━━━━━━━━━━━━━━━']
    for city in cities:
        level = '🔴 Important' if city['players'] > 50 else '🟠 Modéré'
        name = city['name'].replace('\n', ' ').replace('|', '／')[:55]
        line = f"**{name}** ({city['country']}) — **{city['players']}** — {level}"
        if len('\n'.join(lines + [line])) > 3600:
            lines.append('… autres secteurs non affichés (limite Discord)')
            break
        lines.append(line)
    return {'username': 'ЯPTPFR • Info Trafic', 'allowed_mentions': {'parse': []},
            'embeds': [{'title': '🚦 TRAFIC EN DIRECT — VILLES / SECTEURS',
                        'description': '\n'.join(lines), 'color': 0xF59E0B,
                        'footer': {'text': f"ETS2 Simulation 1 • ≥ 20 joueurs • Mis à jour à {now.strftime('%H:%M:%S')} (Paris) • Trucky"},
                        'timestamp': now.isoformat()}]}


def start():
    webhook = os.environ.get('TRAFIC_DISCORD_WEBHOOK_URL', '').strip()
    if not webhook:
        print('[ALERTES TRAFIC] Inactives : TRAFIC_DISCORD_WEBHOOK_URL non configuré.', flush=True)
        return
    if not webhook.startswith(('https://discord.com/api/webhooks/', 'https://discordapp.com/api/webhooks/')):
        print('[ALERTES TRAFIC] URL du webhook invalide.', flush=True)
        return
    webhook = webhook.rstrip('/')
    database_url = os.environ.get('DATABASE_URL', '').strip()
    if not database_url:
        print('[ALERTES TRAFIC] DATABASE_URL requis pour conserver les identifiants après redémarrage.', flush=True)
        return

    # Identité du webhook : ne jamais mélanger les messages de deux salons.
    webhook_key = hashlib.sha256(webhook.encode('utf-8')).hexdigest()
    lock_id = int.from_bytes(hashlib.sha256(webhook_key.encode()).digest()[:8], 'big', signed=True)

    def sync_once():
        # Trucky est consulté avant toute suppression : une panne n'efface rien.
        current, cities = fetch_snapshot()
        with psycopg.connect(database_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                # Verrou PostgreSQL : une seule instance Render publie à la fois.
                cur.execute('SELECT pg_try_advisory_xact_lock(%s)', (lock_id,))
                if not cur.fetchone()[0]:
                    print('[ALERTES TRAFIC] Synchronisation déjà en cours ailleurs.', flush=True)
                    return
                cur.execute('''CREATE TABLE IF NOT EXISTS rptpfr_traffic_discord (
                    webhook_key TEXT NOT NULL,
                    zone_key TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    PRIMARY KEY (webhook_key, zone_key)
                )''')
                cur.execute('SELECT zone_key, message_id, signature FROM rptpfr_traffic_discord WHERE webhook_key=%s', (webhook_key,))
                messages = {key: (message_id, signature) for key, message_id, signature in cur.fetchall()}
                # Tableau UNIQUE des villes/secteurs, indépendant des alertes de bouchons.
                # Son ID est conservé en PostgreSQL comme ceux des bouchons.
                table_key = '__rptpfr_cities_overview__'
                previous_table = messages.pop(table_key, None)
                table_signature = json.dumps(cities, ensure_ascii=False, sort_keys=True)
                if cities:
                    # Mise à jour même sans variation, afin de rafraîchir l'heure affichée.
                    try:
                        body = cities_payload(cities)
                        if previous_table:
                            url = webhook + '/messages/' + urllib.parse.quote(previous_table[0], safe='')
                            try:
                                discord_request(url, 'PATCH', body)
                            except urllib.error.HTTPError as exc:
                                if exc.code != 404:
                                    raise
                                previous_table = None
                        if not previous_table:
                            separator = '&' if '?' in webhook else '?'
                            created = discord_request(webhook + separator + 'wait=true', 'POST', body)
                            if not isinstance(created, dict) or not created.get('id'):
                                raise ValueError('Discord n’a pas retourné l’identifiant du tableau')
                            table_id = str(created['id'])
                        else:
                            table_id = previous_table[0]
                        cur.execute("""INSERT INTO rptpfr_traffic_discord (webhook_key, zone_key, message_id, signature)
                            VALUES (%s,%s,%s,%s) ON CONFLICT (webhook_key,zone_key)
                            DO UPDATE SET message_id=EXCLUDED.message_id, signature=EXCLUDED.signature""",
                            (webhook_key, table_key, table_id, table_signature))
                    except Exception as exc:
                        print('[TRAFIC VILLES] Erreur actualisation du tableau :', repr(exc), flush=True)
                elif previous_table:
                    try:
                        discord_request(webhook + '/messages/' + urllib.parse.quote(previous_table[0], safe=''), 'DELETE')
                        cur.execute('DELETE FROM rptpfr_traffic_discord WHERE webhook_key=%s AND zone_key=%s',
                                    (webhook_key, table_key))
                    except urllib.error.HTTPError as exc:
                        if exc.code == 404:
                            cur.execute('DELETE FROM rptpfr_traffic_discord WHERE webhook_key=%s AND zone_key=%s',
                                        (webhook_key, table_key))
                        else:
                            print('[TRAFIC VILLES] Erreur suppression tableau :', exc.code, flush=True)
                    except Exception as exc:
                        print('[TRAFIC VILLES] Erreur suppression tableau :', repr(exc), flush=True)
                for key, zone in current.items():
                    signature = json.dumps([zone['country'], zone['name'], zone['count'], zone['players']], ensure_ascii=False)
                    record = messages.get(key)
                    if record and record[1] == signature:
                        continue
                    body = payload(zone)
                    try:
                        if record:
                            url = webhook + '/messages/' + urllib.parse.quote(record[0], safe='')
                            discord_request(url, 'PATCH', body)
                            print('[ALERTES TRAFIC] Message modifié :', zone['name'], flush=True)
                        else:
                            separator = '&' if '?' in webhook else '?'
                            created = discord_request(webhook + separator + 'wait=true', 'POST', body)
                            if not isinstance(created, dict) or not created.get('id'):
                                raise ValueError('Discord n’a pas retourné l’identifiant du message')
                            cur.execute('''INSERT INTO rptpfr_traffic_discord (webhook_key, zone_key, message_id, signature)
                                VALUES (%s,%s,%s,%s) ON CONFLICT (webhook_key,zone_key)
                                DO UPDATE SET message_id=EXCLUDED.message_id, signature=EXCLUDED.signature''',
                                (webhook_key, key, str(created['id']), signature))
                            print('[ALERTES TRAFIC] Nouveau message :', zone['name'], flush=True)
                        if record:
                            cur.execute('UPDATE rptpfr_traffic_discord SET signature=%s WHERE webhook_key=%s AND zone_key=%s',
                                        (signature, webhook_key, key))
                    except urllib.error.HTTPError as exc:
                        if record and exc.code == 404:
                            cur.execute('DELETE FROM rptpfr_traffic_discord WHERE webhook_key=%s AND zone_key=%s', (webhook_key, key))
                        print('[ALERTES TRAFIC] Erreur Discord :', exc.code, flush=True)
                    except Exception as exc:
                        print('[ALERTES TRAFIC] Erreur notification :', repr(exc), flush=True)
                for key, (message_id, _) in messages.items():
                    if key in current:
                        continue
                    try:
                        url = webhook + '/messages/' + urllib.parse.quote(message_id, safe='')
                        discord_request(url, 'DELETE')
                        cur.execute('DELETE FROM rptpfr_traffic_discord WHERE webhook_key=%s AND zone_key=%s', (webhook_key, key))
                        print('[ALERTES TRAFIC] Bouchon terminé : message supprimé :', key, flush=True)
                    except urllib.error.HTTPError as exc:
                        if exc.code == 404:
                            cur.execute('DELETE FROM rptpfr_traffic_discord WHERE webhook_key=%s AND zone_key=%s', (webhook_key, key))
                        else:
                            print('[ALERTES TRAFIC] Erreur suppression Discord :', exc.code, flush=True)
                    except Exception as exc:
                        print('[ALERTES TRAFIC] Erreur suppression :', repr(exc), flush=True)
                print('[ALERTES TRAFIC] Zones actives :', len(current), flush=True)

    def worker():
        while True:
            try:
                sync_once()
            except Exception as exc:
                print('[ALERTES TRAFIC] Synchronisation impossible (aucune suppression) :', repr(exc), flush=True)
            time.sleep(POLL_SECONDS)

    threading.Thread(target=worker, name='rptpfr-traffic-discord', daemon=True).start()
    print('[ALERTES TRAFIC] Synchronisation persistante PostgreSQL démarrée (120 secondes).', flush=True)
