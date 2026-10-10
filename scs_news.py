"""Actualités officielles ETS2 depuis Steam (appid 227300)."""
import datetime
import html
import json
import os
import re
import urllib.request
from urllib.parse import urlencode, urlparse

API = 'https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/'
APP_ID = 227300

def fetch_news(count=12):
    url = API + '?' + urlencode({'appid': APP_ID, 'count': count, 'maxlength': 1500, 'format': 'json'})
    req = urllib.request.Request(url, headers={'User-Agent':'RPTPFR-ETS2-News/1.0', 'Accept':'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.load(response)
    items = data.get('appnews', {}).get('newsitems', [])
    if not isinstance(items, list):
        raise ValueError('Réponse Steam inattendue')
    if not items:
        raise ValueError('Steam ne renvoie aucune actualité pour ETS2 (appid 227300)')
    out=[]
    for item in items:
        link = str(item.get('url') or '')
        parsed = urlparse(link)
        # Une publication Steam peut renvoyer vers un site externe.
        # En l'absence de lien HTTPS utilisable, proposer la page officielle ETS2.
        if parsed.scheme != 'https' or not parsed.netloc:
            link = 'https://store.steampowered.com/news/app/227300'
        raw = str(item.get('contents') or '')
        raw = re.sub(r'\[/?(?:img|url|b|i|h\d|list|\*|quote|previewyoutube|table|tr|td)[^\]]*\]', ' ', raw, flags=re.I)
        raw = re.sub(r'<[^>]+>', ' ', raw)
        raw = html.unescape(raw)
        raw = re.sub(r'\s+', ' ', raw).strip()
        out.append({'id':str(item.get('gid') or ''),'title':str(item.get('title') or 'Actualité ETS2')[:250], 'date':int(item.get('date') or 0),'url':link,'summary':raw[:350], 'author':str(item.get('author') or '')[:100]})
    print(f'SCS NEWS: {len(items)} articles reçus de Steam, {len(out)} affichables', flush=True)
    return out

def _db():
    from psycopg import connect
    return connect(os.environ['DATABASE_URL'])

def check_and_notify():
    news=fetch_news(20)
    if not news:
        print('Aucune actualité Steam disponible', flush=True)
        return
    webhook=os.getenv('SCS_NEWS_WEBHOOK_URL','').strip() or os.getenv('DISCORD_WEBHOOK_URL','').strip()
    if not webhook.startswith('https://discord.com/api/webhooks/'):
        raise RuntimeError('Configurer DISCORD_WEBHOOK_URL ou SCS_NEWS_WEBHOOK_URL dans le Cron Job')
    with _db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS scs_news_sent (news_id TEXT PRIMARY KEY, sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW())')
        row=conn.execute('SELECT COUNT(*) FROM scs_news_sent').fetchone()
        if row[0] == 0:
            # Initialisation silencieuse : ne pas publier les anciens articles au premier lancement.
            conn.executemany('INSERT INTO scs_news_sent(news_id) VALUES (%s) ON CONFLICT DO NOTHING',[(n['id'],) for n in news if n['id']])
            print('Initialisation : articles existants mémorisés, aucune ancienne annonce envoyée.',flush=True)
            return
        for n in reversed(news):
            if not n['id'] or conn.execute('SELECT 1 FROM scs_news_sent WHERE news_id=%s',(n['id'],)).fetchone():
                continue
            payload={'username':'RPTPFR • Actualités ETS2','embeds':[{'title':'📰 '+n['title'][:240],'url':n['url'],'description':n['summary'][:500] or 'Nouvelle actualité officielle Euro Truck Simulator 2.', 'color':3447003,'footer':{'text':'SCS Software / Steam • ETS2'},'timestamp':datetime.datetime.fromtimestamp(n['date'],datetime.timezone.utc).isoformat()}], 'allowed_mentions':{'parse':[]}}
            body=json.dumps(payload,ensure_ascii=False).encode('utf-8')
            request=urllib.request.Request(webhook,data=body,method='POST',headers={'Content-Type':'application/json','User-Agent':'RPTPFR-News/1.0'})
            with urllib.request.urlopen(request,timeout=15) as response:
                if response.status not in (200,204):
                    raise RuntimeError('Discord HTTP '+str(response.status))
            conn.execute('INSERT INTO scs_news_sent(news_id) VALUES (%s) ON CONFLICT DO NOTHING',(n['id'],))
            conn.commit()
            print('Annonce envoyée : '+n['title'],flush=True)

if __name__=='__main__':
    check_and_notify()
