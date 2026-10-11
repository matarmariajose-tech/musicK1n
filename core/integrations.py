"""Official API adapters. Secrets come from environment, never from agent input."""
import base64,json,os,re,time,urllib.error,urllib.parse,urllib.request
from datetime import date,timedelta

def http(url,data=None,headers=None,method=None,raw=False):
 req=urllib.request.Request(url,data=data,headers=headers or {},method=method)
 try:
  with urllib.request.urlopen(req,timeout=60) as response:
   body=response.read();return (response.status,dict(response.headers),body) if raw else json.loads(body or b'{}')
 except urllib.error.HTTPError as exc:
  if raw and exc.code==308:return (308,dict(exc.headers),exc.read())
  raise ValueError(f'API respondió HTTP {exc.code}; revisar credenciales, permisos o cuota') from None

def required(key):
 v=os.environ.get(key)
 if not v:raise ValueError(f'Falta configurar {key} en el servicio')
 return v

def google_token():
 from oauth import stored_refresh
 refresh=os.environ.get('GOOGLE_REFRESH_TOKEN') or stored_refresh()
 data=urllib.parse.urlencode({'client_id':required('GOOGLE_CLIENT_ID'),'client_secret':required('GOOGLE_CLIENT_SECRET'),'refresh_token':refresh,'grant_type':'refresh_token'}).encode()
 return http('https://oauth2.googleapis.com/token',data,{'Content-Type':'application/x-www-form-urlencoded'})['access_token']

def sync_spotify(db):
 from engine import ROOT,event
 auth=base64.b64encode((required('SPOTIFY_CLIENT_ID')+':'+required('SPOTIFY_CLIENT_SECRET')).encode()).decode()
 token=http('https://accounts.spotify.com/api/token',b'grant_type=client_credentials',{'Authorization':'Basic '+auth,'Content-Type':'application/x-www-form-urlencoded'})['access_token']
 catalog=json.loads((ROOT/'catalog.json').read_text());ident=catalog['spotify_artist'].rsplit('/',1)[-1]
 albums=[];next_url=f'https://api.spotify.com/v1/artists/{ident}/albums?include_groups=album,single&limit=50'
 while next_url and len(albums)<500:
  if not next_url.startswith('https://api.spotify.com/v1/'):raise ValueError('URL inesperada de Spotify')
  data=http(next_url,headers={'Authorization':'Bearer '+token});albums.extend(data.get('items',[]));next_url=data.get('next')
 result=[{'id':a['id'],'name':a['name'],'release_date':a.get('release_date'),'url':a['external_urls']['spotify']} for a in albums]
 db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('spotify_catalog',json.dumps(result)))
 event(db,'spotify.catalog.synced',{'albums':len(result)});return {'albums':result,'note':'Catálogo público, no estadísticas de Spotify for Artists'}

def sync_youtube(db,p):
 from engine import event,rows
 start=date.fromisoformat(p.get('start',(date.today()-timedelta(days=28)).isoformat()));end=date.fromisoformat(p.get('end',(date.today()-timedelta(days=3)).isoformat()))
 if start>end:raise ValueError('Ventana inválida')
 token=google_token();headers={'Authorization':'Bearer '+token}
 owner=http('https://www.googleapis.com/youtube/v3/channels?part=id,snippet&mine=true',headers=headers)
 allowed=required('YOUTUBE_CHANNEL_ID')
 if not any(c['id']==allowed for c in owner.get('items',[])):raise ValueError('La cuenta autorizada no corresponde al canal configurado')
 total=0
 for e in rows(db,'SELECT id,video_id FROM experiments WHERE video_id IS NOT NULL'):
  params={'ids':'channel==MINE','startDate':start.isoformat(),'endDate':end.isoformat(),'metrics':'views,estimatedMinutesWatched,subscribersGained','filters':'video=='+e['video_id']}
  data=http('https://youtubeanalytics.googleapis.com/v2/reports?'+urllib.parse.urlencode(params),headers=headers)
  values=data.get('rows',[])
  if values:
   v,m,s=values[0]
   db.execute('INSERT INTO metrics VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(experiment_id,platform,window_start,window_end) DO UPDATE SET views=excluded.views,watch_seconds=excluded.watch_seconds,subscribers=excluded.subscribers,source=excluded.source,updated=excluded.updated',(e['id'],'youtube',start.isoformat(),end.isoformat(),int(v),float(m)*60,int(s),'youtube-analytics',time.time()));total+=1
 event(db,'youtube.metrics.synced',{'experiments':total,'start':str(start),'end':str(end)});return {'synced':total,'start':str(start),'end':str(end)}

def upload_private(db,e):
 from engine import DATA,event
 path=(DATA/'clips'/(e['id']+'.mp4')).resolve()
 if not path.is_file() or e['status']!='approved':raise ValueError('Clip no disponible o sin aprobación')
 token=google_token();headers={'Authorization':'Bearer '+token}
 account=http('https://www.googleapis.com/youtube/v3/channels?part=id&mine=true',headers=headers)
 if not any(c['id']==required('YOUTUBE_CHANNEL_ID') for c in account.get('items',[])):raise ValueError('Canal autorizado incorrecto')
 key='upload:'+e['id'];saved=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone();size=path.stat().st_size
 if saved:
  session=saved['value']
  if not session.startswith('https://www.googleapis.com/upload/'):raise ValueError('Sesión inválida')
  status,h,body=http(session,b'',{**headers,'Content-Range':f'bytes */{size}'},'PUT',raw=True)
  if status in (200,201):return finish_upload(db,e,json.loads(body))
  received=h.get('Range',h.get('range'))
  offset=int(received.split('-')[-1])+1 if received else 0
 else:
  body=json.dumps({'snippet':{'title':e['title'],'description':e['caption']+'\n\nEscuchá el disco: '+e['destination'],'categoryId':'10'},'status':{'privacyStatus':'private','selfDeclaredMadeForKids':False}}).encode()
  status,h,_=http('https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',body,{**headers,'Content-Type':'application/json','X-Upload-Content-Length':str(size),'X-Upload-Content-Type':'video/mp4'},'POST',raw=True)
  session=h.get('Location',h.get('location'))
  if not session:raise ValueError('YouTube no devolvió sesión de subida')
  db.execute('INSERT INTO settings VALUES(?,?)',(key,session));db.commit();offset=0
 if not session.startswith('https://www.googleapis.com/upload/'):raise ValueError('Sesión de subida inválida')
 with path.open('rb') as f:f.seek(offset);body=f.read()
 status,h,body=http(session,body,{**headers,'Content-Type':'video/mp4','Content-Range':f'bytes {offset}-{size-1}/{size}'},'PUT',raw=True)
 if status not in (200,201):raise ValueError('Subida incompleta; reintentar para consultar la misma sesión')
 return finish_upload(db,e,json.loads(body))

def finish_upload(db,e,result):
 from engine import event
 vid=result.get('id','')
 if not re.fullmatch(r'[A-Za-z0-9_-]{11}',vid):raise ValueError('Respuesta YouTube inválida')
 with db:
  db.execute('UPDATE experiments SET status="uploaded-private",video_id=? WHERE id=?',(vid,e['id']));event(db,'youtube.uploaded.private',{'id':e['id'],'video_id':vid})
 return {'video_id':vid,'privacy':'private'}
