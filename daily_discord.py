"""Envoi quotidien Discord des challenges RPTPFR. Exécuter via Render Cron Job."""
import os, json, datetime, urllib.request, urllib.error, sys
from zoneinfo import ZoneInfo
import challenges
from server import fetch_all

PARIS=ZoneInfo('Europe/Paris')

def main():
    # Render utilise UTC : execution a 10h et 11h UTC, une seule correspond a midi en France.
    now_paris=datetime.datetime.now(PARIS)
    if now_paris.hour != 12:
        print('Hors horaire de midi Europe/Paris : aucun envoi')
        return
    webhook=os.environ.get('DISCORD_WEBHOOK_URL','').strip()
    token=os.environ.get('TRUCKY_TOKEN','').strip()
    # Le webhook global est facultatif si chaque challenge a le sien.
    if not token:raise RuntimeError('TRUCKY_TOKEN manquant')
    yesterday=(datetime.datetime.now(PARIS).date()-datetime.timedelta(days=1))
    day=yesterday.isoformat()
    challenges.setup()
    with challenges.db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS discord_daily_reports (report_day DATE PRIMARY KEY, sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
        if conn.execute('SELECT 1 FROM discord_daily_reports WHERE report_day=%s',(yesterday,)).fetchone():
            print('Rapport deja envoye pour',day);return
    fetched=fetch_all(token)
    if fetched.get('warning'):raise RuntimeError('Historique Trucky potentiellement incomplet : '+fetched['warning'])
    jobs=fetched['jobs']
    active=[c for c in challenges.list_challenges() if c['active'] and c['start_date']<=yesterday<=c['end_date']]
    if not active:
        print('Aucun challenge actif pour',day);return
    deliveries={}
    for c in active:
        subset=[j for j in jobs if c['start_date'].isoformat()<=j.get('date','')[:10]<=day and (c['transport']=='all' or j.get('vehicle_type')==c['transport'])]
        today=[j for j in subset if j.get('date','')[:10]==day]
        totals={};daily={}
        for j in subset:
            name=j.get('driver','Inconnu');totals[name]=totals.get(name,0)+float(j.get('km',0))
        for j in today:
            name=j.get('driver','Inconnu');daily[name]=daily.get(name,0)+float(j.get('km',0))
        progress=max(totals.values(),default=0) if c['mode']=='individuel' else sum(totals.values())
        top=sorted(daily.items(),key=lambda x:-x[1])[:10]
        ranking='\n'.join(f'{i}. {name[:55]} — +{km:,.0f} km' for i,(name,km) in enumerate(top,1)) or 'Aucun trajet ce jour.'
        icon={'bus':'🚌','camion':'🚛','all':'🚍'}[c['transport']]
        percent=min(100,100*progress/c['target_km'])
        desc=(f'**{progress:,.0f} / {c["target_km"]:,.0f} km** ({percent:.1f} %)\n'
              f'**Aujourd’hui :** +{sum(daily.values()):,.0f} km • {len(daily)} chauffeur(s)\n'
              f'**Classement du jour :**\n{ranking}\n'
              f'**Restant :** {max(0,c["target_km"]-progress):,.0f} km')
        embed={'title':f'{icon} {c["title"][:180]}','description':desc[:4000], 'color':3447003,
                       'footer':{'text':f'{c["mode"].capitalize()} • {c["transport"].upper()} • Trucky RPTPFR'}}
        target=(c.get('discord_webhook') or webhook).strip()
        if not target.startswith('https://discord.com/api/webhooks/'):
            raise RuntimeError('Webhook Discord manquant pour le challenge '+c['title'])
        deliveries.setdefault(target,[]).append(embed)
    # Discord limite les embeds par message à 10
    for target,embeds in deliveries.items():
        for start in range(0,len(embeds),10):
            payload={'username':'RPTPFR Challenges','content':f'🏆 **Bilan des challenges RPTPFR — {yesterday.strftime("%d/%m/%Y")}**', 'embeds':embeds[start:start+10]}
            data=json.dumps(payload,ensure_ascii=False).encode('utf-8')
            req=urllib.request.Request(target,data=data,headers={'Content-Type':'application/json','User-Agent':'RPTPFR-Challenges/1.0'},method='POST')
            with urllib.request.urlopen(req,timeout=30) as response:
                if response.status not in (200,204):raise RuntimeError('Discord HTTP '+str(response.status))
    with challenges.db() as conn:
        conn.execute('INSERT INTO discord_daily_reports(report_day) VALUES (%s) ON CONFLICT DO NOTHING',(yesterday,))
    print('Rapport envoye pour',day)

if __name__=='__main__':main()
