"""RPTPFR shared PostgreSQL player accounts and idempotent game rewards."""
import os, secrets, hashlib, hmac, datetime, re
from psycopg import connect
from psycopg.rows import dict_row

COOKIE = 'rptpfr_player'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS rptpfr_players (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 pseudo VARCHAR(24) NOT NULL,
 pseudo_key VARCHAR(24) NOT NULL UNIQUE,
 code_salt TEXT NOT NULL,
 code_hash TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS rptpfr_sessions (
 token_hash TEXT PRIMARY KEY,
 player_id BIGINT NOT NULL REFERENCES rptpfr_players(id) ON DELETE CASCADE,
 expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS rptpfr_games (
 game_key TEXT NOT NULL,
 match_id TEXT NOT NULL,
 finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 mode TEXT NOT NULL,
 PRIMARY KEY(game_key,match_id)
);
CREATE TABLE IF NOT EXISTS rptpfr_rewards (
 game_key TEXT NOT NULL,
 match_id TEXT NOT NULL,
 player_id BIGINT NOT NULL REFERENCES rptpfr_players(id),
 rank SMALLINT NOT NULL,
 cards_points INTEGER NOT NULL,
 points INTEGER NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(game_key,match_id,player_id),
 FOREIGN KEY(game_key,match_id) REFERENCES rptpfr_games(game_key,match_id)
);
'''
def db():
    url=os.environ.get('DATABASE_URL','')
    if not url: raise RuntimeError('DATABASE_URL absent sur Render')
    return connect(url, row_factory=dict_row, connect_timeout=8)

def setup():
    with db() as conn:
        for statement in SCHEMA.split(';'):
            if statement.strip(): conn.execute(statement)

def digest(code, salt):
    return hashlib.pbkdf2_hmac('sha256',code.encode('utf8'),bytes.fromhex(salt),260000).hex()

def validate(pseudo,code):
    pseudo=str(pseudo).strip()
    if not re.fullmatch(r'[\w .-]{3,24}',pseudo,re.UNICODE): raise ValueError('Pseudo : 3 à 24 caractères (lettres, chiffres, espaces, points, tirets).')
    if not isinstance(code,str) or not 6<=len(code)<=128: raise ValueError('Code secret : 6 caractères minimum.')
    return pseudo,code

def auth(pseudo,code,register=False):
    pseudo,code=validate(pseudo,code)
    with db() as conn:
        row=conn.execute('SELECT * FROM rptpfr_players WHERE pseudo_key=%s',(pseudo.casefold(),)).fetchone()
        if register:
            if row: raise ValueError('Ce pseudo existe déjà. Connecte-toi avec son code.')
            salt=secrets.token_hex(16)
            row=conn.execute('INSERT INTO rptpfr_players(pseudo,pseudo_key,code_salt,code_hash) VALUES (%s,%s,%s,%s) RETURNING *',(pseudo,pseudo.casefold(),salt,digest(code,salt))).fetchone()
        else:
            if not row or not hmac.compare_digest(digest(code,row['code_salt']),row['code_hash']): raise ValueError('Pseudo ou code incorrect.')
        return {'id':row['id'],'pseudo':row['pseudo']}

def new_session(player_id,remember=True):
    token=secrets.token_urlsafe(40)
    seconds=30*86400 if remember else 12*3600
    with db() as conn:
        conn.execute('DELETE FROM rptpfr_sessions WHERE expires_at<NOW()')
        conn.execute('INSERT INTO rptpfr_sessions(token_hash,player_id,expires_at) VALUES (%s,%s,NOW()+(%s * INTERVAL \'1 second\'))',(hashlib.sha256(token.encode()).hexdigest(),player_id,seconds))
    return token,seconds

def session(token):
    if not token:return None
    with db() as conn:
        return conn.execute('SELECT p.id,p.pseudo FROM rptpfr_sessions s JOIN rptpfr_players p ON p.id=s.player_id WHERE s.token_hash=%s AND s.expires_at>NOW()',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()

def logout(token):
    if token:
        with db() as conn: conn.execute('DELETE FROM rptpfr_sessions WHERE token_hash=%s',(hashlib.sha256(token.encode()).hexdigest(),))

def award(match_id,players,winner_id):
    # Only server-owned hands determine rankings. Ties are broken by seat order.
    ranked=sorted(players,key=lambda p:(0 if p['id']==winner_id else 1,sum(card_points(c) for c in p['hand']),players.index(p)))
    mode='bots' if any(p.get('bot') for p in players) else 'multi'
    scale=[20,10,2] if mode=='bots' else [50,25,5]
    with db() as conn:
        inserted=conn.execute('INSERT INTO rptpfr_games(game_key,match_id,mode) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING match_id',('chaos',match_id,mode)).fetchone()
        if not inserted:return []
        rewards=[]
        for rank,p in enumerate(ranked,1):
            points=scale[rank-1] if rank<=3 else 0
            cards=sum(card_points(c) for c in p['hand'])
            if not p.get('bot') and p.get('account_id'):
                conn.execute('INSERT INTO rptpfr_rewards(game_key,match_id,player_id,rank,cards_points,points) VALUES (%s,%s,%s,%s,%s,%s)',('chaos',match_id,p['account_id'],rank,cards,points))
            rewards.append({'name':p['name'],'rank':rank,'cards':cards,'points':points if not p.get('bot') else 0,'bot':bool(p.get('bot'))})
        return rewards

def card_points(card):
    value=card['value']
    return {'skip':20,'reverse':20,'+2':20,'trap':30,'swap':40,'chaos':40,'wild':50,'+4':50}.get(value,int(value) if value.isdigit() else 0)

def leaderboard():
    with db() as conn:
        rows=conn.execute('''SELECT p.pseudo, COALESCE(SUM(r.points),0)::int AS points,COUNT(r.match_id)::int AS games,
        COUNT(*) FILTER(WHERE r.rank=1)::int AS wins
        FROM rptpfr_players p LEFT JOIN rptpfr_rewards r ON r.player_id=p.id
        GROUP BY p.id ORDER BY points DESC,wins DESC,p.pseudo LIMIT 100''').fetchall()
    return [dict(r) for r in rows]
