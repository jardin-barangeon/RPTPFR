"""Classements quotidiens BUS/CAMION et bilans des challenges RPTPFR sur Discord.
Exécution automatique par le Web Service à partir de midi (Europe/Paris).
"""
import datetime
import json
import os
import urllib.request
from zoneinfo import ZoneInfo

import challenges
from server import fetch_all

PARIS = ZoneInfo('Europe/Paris')


def fmt_km(value):
    return f'{value:,.0f}'.replace(',', ' ')


def daily_embed(jobs, kind, day):
    totals = {}
    count = 0
    for job in jobs:
        if job.get('date', '')[:10] != day or job.get('vehicle_type') != kind:
            continue
        name = str(job.get('driver') or 'Inconnu')[:70]
        totals[name] = totals.get(name, 0) + float(job.get('km') or 0)
        count += 1
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0].casefold()))[:10]
    lines = [f'**{rank}.** {name} — **{fmt_km(km)} km**' for rank, (name, km) in enumerate(ranked, 1)]
    return {
        'title': ('🚌 Classement BUS' if kind == 'bus' else '🚛 Classement CAMION'),
        'description': '\n'.join(lines) if lines else 'Aucune mission enregistrée pour cette journée.',
        'color': 3447003 if kind == 'bus' else 15105570,
        'fields': [
            {'name': 'Distance totale', 'value': fmt_km(sum(totals.values())) + ' km', 'inline': True},
            {'name': 'Chauffeurs', 'value': str(len(totals)), 'inline': True},
            {'name': 'Missions', 'value': str(count), 'inline': True},
        ],
        'footer': {'text': 'RPTPFR • Missions terminées Trucky • ' + day},
    }


def challenge_embeds(jobs, yesterday):
    day = yesterday.isoformat()
    output = []
    for c in challenges.list_challenges():
        if not c['active'] or not (c['start_date'] <= yesterday <= c['end_date']):
            continue
        subset = [j for j in jobs if c['start_date'].isoformat() <= j.get('date', '')[:10] <= day
                  and (c['transport'] == 'all' or j.get('vehicle_type') == c['transport'])]
        today = [j for j in subset if j.get('date', '')[:10] == day]
        totals, daily = {}, {}
        for j in subset:
            name = j.get('driver', 'Inconnu')
            totals[name] = totals.get(name, 0) + float(j.get('km') or 0)
        for j in today:
            name = j.get('driver', 'Inconnu')
            daily[name] = daily.get(name, 0) + float(j.get('km') or 0)
        progress = max(totals.values(), default=0) if c['mode'] == 'individuel' else sum(totals.values())
        ranking = '\n'.join(f'{i}. {name[:55]} — +{fmt_km(km)} km'
                            for i, (name, km) in enumerate(sorted(daily.items(), key=lambda x: -x[1])[:10], 1))
        icon = {'bus': '🚌', 'camion': '🚛', 'all': '🚍'}.get(c['transport'], '🏆')
        target = float(c['target_km'])
        percent = min(100, 100 * progress / target) if target > 0 else 0
        desc = (f'**{fmt_km(progress)} / {fmt_km(target)} km** ({percent:.1f} %)\n'
                f'**Hier :** +{fmt_km(sum(daily.values()))} km • {len(daily)} chauffeur(s)\n'
                f'**Classement du jour :**\n{ranking or "Aucun trajet ce jour."}\n'
                f'**Restant :** {fmt_km(max(0, target-progress))} km')
        output.append({'title': f'{icon} {c["title"][:180]}', 'description': desc[:4000],
                       'color': 3447003, 'footer': {'text': f'{c["mode"].capitalize()} • {c["transport"].upper()} • RPTPFR'}})
    return output


def post_discord(webhook, content, embeds):
    for offset in range(0, len(embeds), 10):
        payload = {'username': 'RPTPFR • Classements', 'content': content if offset == 0 else '',
                   'embeds': embeds[offset:offset+10], 'allowed_mentions': {'parse': []}}
        req = urllib.request.Request(webhook, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                                     headers={'Content-Type': 'application/json', 'User-Agent': 'RPTPFR-Daily/2.0'}, method='POST')
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status not in (200, 204):
                raise RuntimeError('Discord HTTP ' + str(response.status))


def main(force=False):
    """Envoi quotidien avec verrou PostgreSQL anti-doublon, même sur plusieurs instances."""
    now = datetime.datetime.now(PARIS)
    print('Heure Europe/Paris :', now.isoformat(), flush=True)
    if not force and now.hour < 12 and os.getenv('ALLOW_MANUAL_RUN') != '1':
        print('Avant midi Europe/Paris : aucun envoi.', flush=True)
        return False
    webhook = os.getenv('DISCORD_WEBHOOK_URL', '').strip()
    token = os.getenv('TRUCKY_TOKEN', '').strip()
    if not webhook.startswith('https://discord.com/api/webhooks/'):
        raise RuntimeError('DISCORD_WEBHOOK_URL manquant ou invalide sur le Web Service Render')
    if not token:
        raise RuntimeError('TRUCKY_TOKEN manquant sur le Web Service Render')
    yesterday = now.date() - datetime.timedelta(days=1)
    day = yesterday.isoformat()
    challenges.setup()
    # Le verrou est gardé pendant tout l'envoi, afin d'éviter deux messages
    # si Render démarre plusieurs processus/instances en même temps.
    with challenges.db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS discord_daily_reports (report_day DATE PRIMARY KEY, sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW())')
        acquired = conn.execute('SELECT pg_try_advisory_xact_lock(%s)', (221541200,)).fetchone()['pg_try_advisory_xact_lock']
        if not acquired:
            print('Un autre processus prépare déjà le rapport.', flush=True)
            return False
        if not force and conn.execute('SELECT 1 FROM discord_daily_reports WHERE report_day=%s', (yesterday,)).fetchone():
            print('Rapport déjà envoyé pour', day, flush=True)
            return False
        fetched = fetch_all(token)
        jobs = fetched['jobs']
        print('Missions récupérées :', len(jobs), '| avertissement :', fetched.get('warning') or 'aucun', flush=True)
        embeds = [daily_embed(jobs, 'camion', day), daily_embed(jobs, 'bus', day)]
        try:
            embeds.extend(challenge_embeds(jobs, yesterday))
        except Exception as exc:
            # Un problème sur les challenges ne doit pas empêcher les deux classements.
            print('Bilan challenges indisponible :', repr(exc), flush=True)
        content = f'📊 **Classements quotidiens RPTPFR — {yesterday.strftime("%d/%m/%Y")}**'
        if fetched.get('warning'):
            content += '\n⚠️ Historique Trucky possiblement incomplet : classements indicatifs.'
        post_discord(webhook, content, embeds)
        if not force:
            conn.execute('INSERT INTO discord_daily_reports(report_day) VALUES (%s) ON CONFLICT DO NOTHING', (yesterday,))
        conn.commit()
    print('Classements BUS/CAMION envoyés pour', day, flush=True)
    return True


if __name__ == '__main__':
    main()
