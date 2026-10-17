"""Alertes de circulation ETS2 SIM1 vers Discord, indépendantes des visiteurs du site."""
import datetime
import json
import os
import threading
import time
import urllib.request
from zoneinfo import ZoneInfo

TRAFFIC_URL = 'https://api.truckyapp.com/v2/traffic?game=ets2&server=sim1'
PARIS = ZoneInfo('Europe/Paris')
POLL_SECONDS = 120
# N'alerter à nouveau sur une même zone qu'en cas d'aggravation (ou après disparition).

def fetch_jams():
    req = urllib.request.Request(TRAFFIC_URL, headers={'Accept': 'application/json', 'User-Agent': 'RPTPFR-Traffic-Alerts/1.0'})
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


def send_alert(webhook, zone, aggravated=False):
    now = datetime.datetime.now(PARIS)
    heading = '🔴 BOUCHON EN AGGRAVATION' if aggravated else '🚨 NOUVEAU BOUCHON SIGNALÉ'
    desc = ('**📍 Secteur :** {name}\n**🌍 Pays :** {country}\n'
            '**🚧 Embouteillage(s) :** {count}\n**🚗 Joueurs concernés :** {players}\n'
            '**🎮 Serveur :** ETS2 — Simulation 1\n**🕒 Heure :** {hour} (Paris)').format(
                **zone, hour=now.strftime('%H:%M:%S'))
    body = {'username': 'ЯPTPFR • Info Trafic',
            'allowed_mentions': {'parse': []},
            'embeds': [{'title': heading, 'description': desc, 'color': 0xE34B4B,
                        'footer': {'text': 'Alerte trafic façon Coyote • Source : Trucky • ЯPTPFR'},
                        'timestamp': now.isoformat()}]}
    request = urllib.request.Request(webhook, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                     headers={'Content-Type': 'application/json', 'User-Agent': 'RPTPFR-Traffic-Alerts/1.0'}, method='POST')
    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()


def start():
    webhook = os.environ.get('TRAFIC_DISCORD_WEBHOOK_URL', '').strip()
    if not webhook:
        print('[ALERTES TRAFIC] Inactives : TRAFIC_DISCORD_WEBHOOK_URL non configuré.', flush=True)
        return
    if not webhook.startswith(('https://discord.com/api/webhooks/', 'https://discordapp.com/api/webhooks/')):
        print('[ALERTES TRAFIC] URL du webhook invalide.', flush=True)
        return

    def worker():
        previous = {}
        while True:
            try:
                current = fetch_jams()
                for key, zone in current.items():
                    old = previous.get(key)
                    aggravated = old is not None and (zone['count'] > old['count'] or zone['players'] >= old['players'] + 5)
                    if old is None or aggravated:
                        try:
                            send_alert(webhook, zone, aggravated=aggravated)
                            print('[ALERTES TRAFIC] Envoyée :', zone['country'], zone['name'], flush=True)
                        except Exception as exc:
                            print('[ALERTES TRAFIC] Envoi impossible :', repr(exc), flush=True)
                            # Nouvelle tentative au prochain passage, sans marquer comme déjà notifié.
                            if old is None:
                                continue
                    previous[key] = zone
                # Les bouchons disparus quittent l'état, permettant une alerte à leur retour.
                previous = {key: previous[key] for key in current if key in previous}
                print('[ALERTES TRAFIC] Vérification terminée :', len(current), 'zone(s) avec bouchon.', flush=True)
            except Exception as exc:
                print('[ALERTES TRAFIC] Trucky indisponible :', repr(exc), flush=True)
            time.sleep(POLL_SECONDS)

    threading.Thread(target=worker, name='rptpfr-traffic-discord', daemon=True).start()
    print('[ALERTES TRAFIC] Surveillance démarrée (ETS2 Simulation 1, toutes les 2 minutes).', flush=True)
