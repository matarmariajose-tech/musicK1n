import base64, hashlib, json, os, secrets, time, urllib.parse
from cryptography.fernet import Fernet
from integrations import http,required

def cipher():
 key=required('TOKEN_ENCRYPTION_KEY')
 if len(key)<32:raise ValueError('TOKEN_ENCRYPTION_KEY requiere al menos 32 caracteres')
 return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))
def start(db):
 required('GOOGLE_CLIENT_SECRET');cipher();state=secrets.token_urlsafe(32)
 redirect=required('PUBLIC_URL').rstrip('/')+'/oauth/google/callback'
 db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('google_oauth_state',json.dumps({'hash':hashlib.sha256(state.encode()).hexdigest(),'created':time.time()})))
 params={'client_id':required('GOOGLE_CLIENT_ID'),'redirect_uri':redirect,'response_type':'code','scope':'https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly','access_type':'offline','prompt':'consent','state':state}
 return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urllib.parse.urlencode(params)}

def finish(db,p):
 state=db.execute('SELECT value FROM settings WHERE key="google_oauth_state"').fetchone()
 if not state:raise ValueError('Autorización no iniciada')
 value=json.loads(state['value'])
 if not secrets.compare_digest(value['hash'],hashlib.sha256(p.get('state','').encode()).hexdigest()) or time.time()-value['created']>600:raise ValueError('Autorización vencida o inválida')
 db.execute('DELETE FROM settings WHERE key="google_oauth_state"');db.commit()
 data=urllib.parse.urlencode({'code':p.get('code',''),'client_id':required('GOOGLE_CLIENT_ID'),'client_secret':required('GOOGLE_CLIENT_SECRET'),'redirect_uri':required('PUBLIC_URL').rstrip('/')+'/oauth/google/callback','grant_type':'authorization_code'}).encode()
 tokens=http('https://oauth2.googleapis.com/token',data,{'Content-Type':'application/x-www-form-urlencoded'})
 if not tokens.get('refresh_token'):raise ValueError('Google no devolvió refresh token; revocar acceso anterior y reautorizar')
 channels=http('https://www.googleapis.com/youtube/v3/channels?part=id,snippet&mine=true',headers={'Authorization':'Bearer '+tokens['access_token']})
 if not any(c['id']==required('YOUTUBE_CHANNEL_ID') for c in channels.get('items',[])):raise ValueError('Se autorizó otro canal. Revisá YOUTUBE_CHANNEL_ID y la cuenta seleccionada')
 encrypted=cipher().encrypt(tokens['refresh_token'].encode()).decode()
 db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('google_refresh',encrypted));db.commit()
 return {'connected':True}

def stored_refresh():
 from engine import database
 db=database();r=db.execute('SELECT value FROM settings WHERE key="google_refresh"').fetchone();db.close()
 if not r:raise ValueError('Conectar YouTube desde el panel')
 return cipher().decrypt(r['value'].encode()).decode()
