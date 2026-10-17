"""Synchronise les messages Discord avec les bouchons actifs ETS2 SIM1."""
import datetime
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

TRAFFIC_URL = 'https://api.truckyapp.com/v2/traffic?game=ets2&server=sim1'
PARIS = ZoneInfo('Europe/Paris')
POLL_SECONDS = 120


def fetch_jams():
    req = urllib.request.Request(TRAFFIC_URL, headers={'Accept': 'application/json', 'User-Agent': 'RPTPFR-Traffic-Alerts/2.0'})
    with urllib.request.urlopen(req, timeout=18) as response:
        data = json.load(response)
    countries = data.get('response') if isinstance(data, dict) else None
    if not isinstance(countries, list):
        raise ValueError('Réponse Trucky invalide')
    result = {}
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
            if not count:
                continue
            country = str(group.get('country') or loc.get('country') or 'Pays inconnu')[:80]
            name = str(loc.get('name') or 'Zone inconnue')[:120]
            key = str(loc.get('layerID') or (country + '|' + name))
            result[key] = {'country': country, 'name': name, 'count': count, 'players': players}
    return result


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


def start():
    webhook = os.environ.get('TRAFIC_DISCORD_WEBHOOK_URL', '').strip()
    if not webhook:
        print('[ALERTES TRAFIC] Inactives : TRAFIC_DISCORD_WEBHOOK_URL non configuré.', flush=True)
        return
    if not webhook.startswith(('https://discord.com/api/webhooks/', 'https://discordapp.com/api/webhooks/')):
        print('[ALERTES TRAFIC] URL du webhook invalide.', flush=True)
        return
    webhook = webhook.rstrip('/')
    # Un message par zone, mis à jour ou supprimé suivant son état.
    # Discord renvoie l'identifiant du message grâce à wait=true.
    def worker():
        messages = {}
        while True:
            try:
                current = fetch_jams()
                for key, zone in current.items():
                    record = messages.get(key)
                    signature = (zone['country'], zone['name'], zone['count'], zone['players'])
                    if record and record['signature'] == signature:
                        continue
                    body = payload(zone)
                    try:
                        if record:
                            url = webhook + '/messages/' + urllib.parse.quote(record['id'], safe='')
                            discord_request(url, 'PATCH', body)
                            print('[ALERTES TRAFIC] Actualisée :', zone['name'], flush=True)
                        else:
                            separator = '&' if '?' in webhook else '?'
                            created = discord_request(webhook + separator + 'wait=true', 'POST', body)
                            if not isinstance(created, dict) or not created.get('id'):
                                raise ValueError('Discord n’a pas retourné d’identifiant de message')
                            messages[key] = {'id': str(created['id']), 'signature': signature}
                            print('[ALERTES TRAFIC] Nouvelle :', zone['name'], flush=True)
                        messages[key]['signature'] = signature
                    except urllib.error.HTTPError as exc:
                        if record and exc.code == 404:
                            messages.pop(key, None)  # message supprimé manuellement : recréation au prochain cycle
                        print('[ALERTES TRAFIC] Erreur Discord :', exc.code, flush=True)
                    except Exception as exc:
                        print('[ALERTES TRAFIC] Erreur notification :', repr(exc), flush=True)
                for key in list(messages):
                    if key in current:
                        continue
                    try:
                        url = webhook + '/messages/' + urllib.parse.quote(messages[key]['id'], safe='')
                        discord_request(url, 'DELETE')
                        messages.pop(key, None)
                        print('[ALERTES TRAFIC] Bouchon terminé : message supprimé.', flush=True)
                    except urllib.error.HTTPError as exc:
                        if exc.code == 404:
                            messages.pop(key, None)
                        else:
                            print('[ALERTES TRAFIC] Suppression impossible :', exc.code, flush=True)
                    except Exception as exc:
                        print('[ALERTES TRAFIC] Suppression impossible :', repr(exc), flush=True)
                print('[ALERTES TRAFIC] Zones actives :', len(current), flush=True)
            except Exception as exc:
                # Ne jamais supprimer les alertes si Trucky ne répond pas.
                print('[ALERTES TRAFIC] Trucky indisponible :', repr(exc), flush=True)
            time.sleep(POLL_SECONDS)

    threading.Thread(target=worker, name='rptpfr-traffic-discord', daemon=True).start()
    print('[ALERTES TRAFIC] Synchronisation Discord démarrée (120 secondes).', flush=True)
