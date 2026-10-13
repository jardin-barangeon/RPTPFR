"""TOP 5 mensuels BUS/CAMION et bilans quotidiens des challenges RPTPFR sur Discord.
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
    # Classement du mois en cours, arrêté à la veille du rapport.
    # Le filtrage ISO YYYY-MM-DD est fiable pour ces dates normalisées.
    month_start = day[:7] + '-01'
    totals = {}
    count = 0
    for job in jobs:
        job_date = str(job.get('date') or '')[:10]
        if not (month_start <= job_date <= day) or job.get('vehicle_type') != kind:
            continue
        name = str(job.get('driver') or 'Inconnu')[:70]
        totals[name] = totals.get(name, 0) + float(job.get('km') or 0)
        count += 1
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0].casefold()))[:5]
    lines = [f'**{rank}.** {name} — **{fmt_km(km)} km**' for rank, (name, km) in enumerate(ranked, 1)]
    return {
        'title': ('🚌 TOP 5 BUS — mois en cours' if kind == 'bus' else '🚛 TOP 5 CAMION — mois en cours'),
        'description': '\n'.join(lines) if lines else 'Aucune mission enregistrée pour ce mois.',
        'color': 3447003 if kind == 'bus' else 15105570,
        'fields': [
            {'name': 'Distance totale', 'value': fmt_km(sum(totals.values())) + ' km', 'inline': True},
            {'name': 'Chauffeurs', 'value': str(len(totals)), 'inline': True},
            {'name': 'Missions', 'value': str(count), 'inline': True},
        ],
        'footer': {'text': 'RPTPFR • Missions terminées Trucky • ' + month_start + ' au ' + day},
    }


def challenge_embeds(jobs, yesterday):
    """Uniquement les challenges en cours, classement collectif complet."""
    day = yesterday.isoformat()
    output = []
    for c in challenges.list_challenges():
        if not c['active'] or not (c['start_date'] <= yesterday <= c['end_date']):
            continue
        subset = [j for j in jobs
                  if c['start_date'].isoformat() <= str(j.get('date') or '')[:10] <= day
                  and (c['transport'] == 'all' or j.get('vehicle_type') == c['transport'])]
        totals = {}
        for j in subset:
            name = str(j.get('driver') or 'Inconnu')
            totals[name] = totals.get(name, 0) + float(j.get('km') or 0)
        ranked = sorted(totals.items(), key=lambda x: (-x[1], x[0].casefold()))
        icon = {'bus': '🚌', 'camion': '🚛', 'all': '🚌🚛'}.get(c['transport'], '🏆')
        # Mise en page Discord : vrais retours à la ligne et champs séparés.
        lines = [f'**{i}.** {name[:55]} — **{fmt_km(km)} km**'
                 for i, (name, km) in enumerate(ranked, 1)]
        description = ('\n'.join(lines) if lines else 'Aucune mission pour le moment.')
        # Discord limite la description d'un embed à 4096 caractères.
        if len(description) > 4000:
            description = description[:3980].rsplit('\n', 1)[0] + '\n…'
        output.append({
            'title': f'{icon} {c["title"][:180]}',
            'description': '**🏆 Classement général du challenge**\n\n' + description,
            'color': 3447003 if c['transport'] == 'bus' else 15105570,
            'fields': [
                {'name': '📏 Distance totale', 'value': f'**{fmt_km(sum(totals.values()))} km**', 'inline': True},
                {'name': '👥 Chauffeurs participants', 'value': str(len(totals)), 'inline': True},
                {'name': '🚚 Missions', 'value': str(len(subset)), 'inline': True},
            ],
            'footer': {'text': f'Challenge collectif • {c["transport"].upper()} • RPTPFR'},
        })
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
        content = (f'📊 **TOP 5 mensuel CAMION / BUS RPTPFR — {yesterday.strftime("%m/%Y")}**'
                   f'\n*Cumul du 01/{yesterday.strftime("%m/%Y")} au {yesterday.strftime("%d/%m/%Y")} inclus*')
        if fetched.get('warning'):
            content += '\n⚠️ Historique Trucky possiblement incomplet : classements indicatifs.'
        post_discord(webhook, content, embeds)
        if not force:
            conn.execute('INSERT INTO discord_daily_reports(report_day) VALUES (%s) ON CONFLICT DO NOTHING', (yesterday,))
        conn.commit()
    print('TOP 5 mensuels BUS/CAMION envoyés, arrêtés au', day, flush=True)
    return True


if __name__ == '__main__':
    main()
