"""Persistent K1N workflow. CLI RPC uses JSON stdin; no shell interpolation."""
import csv, io, json, os, re, sqlite3, subprocess, sys, time, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
DATA=Path(os.environ.get('K1N_DATA_DIR',str(ROOT/'data'))).resolve()

def database():
 DATA.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(DATA/'k1n.sqlite',timeout=20);db.row_factory=sqlite3.Row
 db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA foreign_keys=ON')
 db.executescript('''
 CREATE TABLE IF NOT EXISTS tracks(id TEXT PRIMARY KEY,title TEXT NOT NULL,audio TEXT,duration REAL,spotify_url TEXT,lyrics TEXT DEFAULT '',story TEXT DEFAULT '',created REAL);
 CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,name TEXT,kind TEXT,path TEXT UNIQUE,duration REAL);
 CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY,track_id TEXT REFERENCES tracks(id),start REAL,end REAL,style TEXT,title TEXT,caption TEXT,destination TEXT,status TEXT DEFAULT 'draft',clip TEXT,video_id TEXT,created REAL,UNIQUE(track_id,start,end,style));
 CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,experiment_id TEXT REFERENCES experiments(id),kind TEXT,status TEXT,error TEXT,created REAL,started REAL,finished REAL);
 CREATE UNIQUE INDEX IF NOT EXISTS active_job ON jobs(experiment_id,kind) WHERE status IN ('queued','running');
 CREATE TABLE IF NOT EXISTS metrics(experiment_id TEXT REFERENCES experiments(id),platform TEXT,window_start TEXT,window_end TEXT,views INTEGER,watch_seconds REAL,subscribers INTEGER,source TEXT,updated REAL,PRIMARY KEY(experiment_id,platform,window_start,window_end));
 CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,event TEXT,detail TEXT,created REAL);
 CREATE TABLE IF NOT EXISTS contacts(id TEXT PRIMARY KEY,name TEXT,url TEXT,email TEXT,reason TEXT,draft TEXT,status TEXT DEFAULT 'draft',UNIQUE(email));
 CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
 ''');return db

def event(db,name,detail):db.execute('INSERT INTO audit(event,detail,created) VALUES(?,?,?)',(name,json.dumps(detail,ensure_ascii=False),time.time()))
def rows(db,q,args=()):return [dict(r) for r in db.execute(q,args)]
def text(v,limit=500):
 if not isinstance(v,str) or not v.strip() or len(v)>limit:raise ValueError('Texto vacío o demasiado largo')
 return v.strip()
def url(v):
 if not isinstance(v,str) or not re.match(r'^https://(www\.)?(youtube\.com|youtu\.be|open\.spotify\.com)/',v):raise ValueError('Destino debe ser YouTube o Spotify HTTPS')
 return v

def asset_path(identifier,kind=None):
 if not re.fullmatch(r'[a-f0-9]{32}',identifier):raise ValueError('Id de archivo inválido')
 db=database();a=db.execute('SELECT * FROM assets WHERE id=?',(identifier,)).fetchone();db.close()
 if not a or (kind and a['kind']!=kind):raise ValueError('Archivo no encontrado')
 p=Path(a['path']).resolve()
 if not p.is_relative_to(DATA):raise ValueError('Archivo fuera de almacenamiento')
 return p

def register_asset(db,p):
 ident=p['id'];kind=p['kind']
 if kind not in ('audio','cover') or not re.fullmatch(r'[a-f0-9]{32}',ident):raise ValueError('Archivo inválido')
 path=DATA/'uploads'/ident
 if not path.is_file():raise ValueError('Archivo faltante')
 probe=subprocess.run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)],capture_output=True,text=True,timeout=20)
 if probe.returncode:raise ValueError('No se pudo leer el audio o imagen')
 meta=json.loads(probe.stdout);streams=meta.get('streams',[])
 duration=float(meta.get('format',{}).get('duration',0))
 if kind=='audio' and (not any(s.get('codec_type')=='audio' for s in streams) or not 0<duration<=7200):raise ValueError('Se necesita audio de hasta 2 horas')
 if kind=='cover' and not any(s.get('codec_type')=='video' and 0<s.get('width',0)<=8192 and 0<s.get('height',0)<=8192 for s in streams):raise ValueError('Portada inválida')
 db.execute('INSERT INTO assets VALUES(?,?,?,?,?)',(ident,text(p['name']),kind,str(path),duration));return {'id':ident,'duration':duration}

def dispatch(db,action,p):
 if action=='campaign':return json.loads((ROOT/'campaign.json').read_text())
 if action=='overview':
  return {'tracks':rows(db,'SELECT * FROM tracks ORDER BY created DESC'),'assets':rows(db,'SELECT id,name,kind,duration FROM assets'),'experiments':rows(db,'SELECT e.*,t.title AS track_title FROM experiments e JOIN tracks t ON t.id=e.track_id ORDER BY e.created DESC'),'jobs':rows(db,'SELECT * FROM jobs ORDER BY created DESC LIMIT 50'),'metrics':rows(db,'SELECT * FROM metrics'),'contacts':rows(db,'SELECT * FROM contacts'),'catalog':json.loads((ROOT/'catalog.json').read_text()),'connections':{'google':bool(os.environ.get('GOOGLE_REFRESH_TOKEN') or db.execute('SELECT 1 FROM settings WHERE key="google_refresh"').fetchone()),'spotify':bool(os.environ.get('SPOTIFY_CLIENT_ID') and os.environ.get('SPOTIFY_CLIENT_SECRET')),'model':bool(os.environ.get('AI_GATEWAY_API_KEY'))}}
 if action=='oauth-start':
  from oauth import start
  return start(db)
 if action=='oauth-finish':
  from oauth import finish
  return finish(db,p)
 if action=='asset':return register_asset(db,p)
 if action=='track':
  aid=text(p['audio']);ap=asset_path(aid,'audio');a=db.execute('SELECT duration FROM assets WHERE id=?',(aid,)).fetchone()
  ident=uuid.uuid4().hex;destination=p.get('spotify_url','')
  if destination:url(destination)
  db.execute('INSERT INTO tracks VALUES(?,?,?,?,?,?,?,?)',(ident,text(p['title']),aid,a['duration'],destination,p.get('lyrics','')[:10000],p.get('story','')[:10000],time.time()))
  event(db,'track.created',{'id':ident});return {'id':ident}
 if action=='experiment':
  t=db.execute('SELECT * FROM tracks WHERE id=?',(p['track_id'],)).fetchone()
  if not t:raise ValueError('Canción no encontrada')
  start,end=float(p['start']),float(p['end'])
  if not 0<=start<end<=t['duration'] or not 5<=end-start<=60:raise ValueError('Corte debe durar 5–60 segundos dentro del audio')
  style=p['style']
  if style not in ('cover','waveform'):raise ValueError('Formato inválido')
  ident=uuid.uuid4().hex
  try:db.execute('INSERT INTO experiments(id,track_id,start,end,style,title,caption,destination,created) VALUES(?,?,?,?,?,?,?,?,?)',(ident,t['id'],start,end,style,text(p.get('title',t['title']),100),p.get('caption','')[:5000],url(p['destination']),time.time()))
  except sqlite3.IntegrityError:
   e=db.execute('SELECT id FROM experiments WHERE track_id=? AND start=? AND end=? AND style=?',(t['id'],start,end,style)).fetchone();return {'id':e['id'],'existing':True}
  event(db,'experiment.created',{'id':ident});return {'id':ident}
 if action=='render':
  e=db.execute('SELECT * FROM experiments WHERE id=?',(p['id'],)).fetchone()
  if not e:raise ValueError('Experimento no encontrado')
  if e['status'] not in ('draft','rendered'):raise ValueError('No se puede renderizar en este estado')
  ident=uuid.uuid4().hex
  try:db.execute('INSERT INTO jobs(id,experiment_id,kind,status,created) VALUES(?,?,?,?,?)',(ident,e['id'],'render','queued',time.time()))
  except sqlite3.IntegrityError:return {'queued':False,'reason':'Ya está en cola'}
  event(db,'render.queued',{'id':e['id']});return {'job_id':ident}
 if action=='upload-private':
  e=db.execute('SELECT * FROM experiments WHERE id=?',(p['id'],)).fetchone()
  if not e or e['status']!='approved':raise ValueError('Se necesita aprobación previa')
  if p.get('confirm')!='UPLOAD_PRIVATE':raise ValueError('Confirmación de subida requerida')
  from integrations import required
  for key in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','YOUTUBE_CHANNEL_ID'):required(key)
  ident=uuid.uuid4().hex
  try:db.execute('INSERT INTO jobs(id,experiment_id,kind,status,created) VALUES(?,?,?,?,?)',(ident,e['id'],'upload','queued',time.time()))
  except sqlite3.IntegrityError:return {'queued':False,'reason':'Ya está en cola'}
  event(db,'youtube.upload.authorized',{'id':e['id'],'privacy':'private'});return {'job_id':ident}
 if action=='approve':
  e=db.execute('SELECT * FROM experiments WHERE id=?',(p['id'],)).fetchone()
  if not e or e['status']!='rendered':raise ValueError('Primero renderizá y revisá el clip')
  if db.execute('SELECT 1 FROM jobs WHERE experiment_id=? AND status IN ("queued","running")',(e['id'],)).fetchone():raise ValueError('Esperá a que termine el render')
  db.execute('UPDATE experiments SET status="approved" WHERE id=?',(e['id'],));event(db,'experiment.approved',{'id':e['id']});return {'approved':True}
 if action=='published':
  e=db.execute('SELECT * FROM experiments WHERE id=?',(p['id'],)).fetchone()
  if not e or e['status']!='approved':raise ValueError('Primero aprobá el clip')
  vid=text(p['video_id'],20)
  if not re.fullmatch(r'[A-Za-z0-9_-]{11}',vid):raise ValueError('Id YouTube inválido')
  db.execute('UPDATE experiments SET status="published",video_id=? WHERE id=?',(vid,e['id']));event(db,'experiment.published.manual',{'id':e['id'],'video_id':vid});return {'saved':True}
 if action=='metrics':
  parsed=list(csv.DictReader(io.StringIO(p['csv'])))
  if len(parsed)>10000:raise ValueError('Máximo 10000 filas')
  for r in parsed:
   if r['platform'] not in ('youtube','spotify'):raise ValueError('Plataforma inválida')
   from datetime import date
   if date.fromisoformat(r['window_start'])>date.fromisoformat(r['window_end']):raise ValueError('Fechas invertidas')
   v,w,s=int(r['views']),float(r['watch_seconds']),int(r['subscribers'])
   if v<0 or w<0 or not __import__('math').isfinite(w):raise ValueError('Métricas inválidas')
   db.execute('INSERT INTO metrics VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(experiment_id,platform,window_start,window_end) DO UPDATE SET views=excluded.views,watch_seconds=excluded.watch_seconds,subscribers=excluded.subscribers,source=excluded.source,updated=excluded.updated',(r['experiment_id'],r['platform'],r['window_start'],r['window_end'],v,w,s,'csv',time.time()))
  event(db,'metrics.imported',{'rows':len(parsed)});return {'imported':len(parsed)}
 if action=='report':
  data=rows(db,'SELECT m.*,e.track_id,e.style,e.start,e.end FROM metrics m JOIN experiments e ON e.id=m.experiment_id')
  for r in data:
   r['avg_watch_seconds']=r['watch_seconds']/r['views'] if r['views'] else None
   r['evidence']='muestra pequeña' if r['views']<100 else 'comparar solo misma plataforma y ventana'
  return {'results':data,'note':'No atribuir escuchas Spotify a un clip sin evidencia. Comparar ventanas iguales. Ningún gasto automático.'}
 if action=='contact':
  source=text(p['url'],1000)
  if not source.startswith('https://'):raise ValueError('Contacto requiere fuente pública HTTPS')
  email=text(p['email'])
  if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise ValueError('Correo inválido')
  ident=uuid.uuid4().hex;db.execute('INSERT INTO contacts(id,name,url,email,reason,draft) VALUES(?,?,?,?,?,?)',(ident,text(p['name']),source,email.lower(),text(p['reason'],2000),p.get('draft','')[:5000]));return {'id':ident}
 if action in ('spotify-sync','youtube-sync'): 
  from integrations import sync_spotify,sync_youtube
  return sync_spotify(db) if action=='spotify-sync' else sync_youtube(db,p)
 raise ValueError('Acción desconocida')

def render(db,job):
 e=db.execute('SELECT * FROM experiments WHERE id=?',(job['experiment_id'],)).fetchone();t=db.execute('SELECT * FROM tracks WHERE id=?',(e['track_id'],)).fetchone()
 audio=asset_path(t['audio'],'audio');clips=DATA/'clips';clips.mkdir(exist_ok=True)
 out=clips/(e['id']+'.mp4');tmp=clips/(e['id']+'.tmp.mp4');duration=e['end']-e['start']
 if e['style']=='cover':
  a=db.execute('SELECT id FROM assets WHERE kind="cover" ORDER BY rowid DESC LIMIT 1').fetchone()
  if not a:raise ValueError('Cargá una portada para este formato')
  args=['-loop','1','-i',str(asset_path(a['id'],'cover')),'-ss',str(e['start']),'-i',str(audio),'-vf','scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=0x101017,setsar=1','-map','0:v:0','-map','1:a:0']
 else:
  args=['-ss',str(e['start']),'-i',str(audio),'-filter_complex','[0:a]asplit[a][w];[w]showwaves=s=720x1280:mode=line:colors=0xa78bfa:rate=30,format=yuv420p[v]','-map','[v]','-map','[a]']
 cmd=['ffmpeg','-nostdin','-v','error','-y',*args,'-t',str(duration),'-r','30','-c:v','libx264','-preset','veryfast','-threads','2','-c:a','aac','-b:a','192k','-pix_fmt','yuv420p','-movflags','+faststart',str(tmp)]
 try:
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=300)
  if r.returncode:raise ValueError('FFmpeg no pudo generar el clip')
  tmp.replace(out)
  with db:
   db.execute('UPDATE experiments SET status="rendered",clip=? WHERE id=?',(str(out),e['id']));event(db,'render.completed',{'id':e['id']})
 finally:tmp.unlink(missing_ok=True)

def worker_once():
 db=database()
 # Single worker process; interrupted jobs are marked failed on worker startup.
 db.execute('BEGIN IMMEDIATE');job=db.execute('SELECT * FROM jobs WHERE status="queued" ORDER BY created LIMIT 1').fetchone()
 if not job:db.commit();db.close();return False
 db.execute('UPDATE jobs SET status="running",started=? WHERE id=?',(time.time(),job['id']));db.commit()
 try:
  if job['kind']=='render':render(db,job)
  elif job['kind']=='upload':
   from integrations import upload_private
   upload_private(db,db.execute('SELECT * FROM experiments WHERE id=?',(job['experiment_id'],)).fetchone())
  else:raise ValueError('Tipo de trabajo inválido')
  with db:db.execute('UPDATE jobs SET status="done",finished=? WHERE id=?',(time.time(),job['id']))
 except Exception as exc:
  with db:db.execute('UPDATE jobs SET status="failed",error=?,finished=? WHERE id=?',(str(exc)[:300],time.time(),job['id']))
 finally:db.close()
 return True

def main():
 if len(sys.argv)>1 and sys.argv[1]=='worker':
  import fcntl
  DATA.mkdir(parents=True,exist_ok=True);lock=open(DATA/'worker.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  db=database()
  with db:db.execute('UPDATE jobs SET status="failed",error="Proceso interrumpido; volver a solicitar render" WHERE status="running"')
  db.close()
  while True:
   if not worker_once():time.sleep(2)
 else:
  db=database()
  try:
   req=json.load(sys.stdin)
   with db:result=dispatch(db,req['action'],req.get('payload',{}))
   print(json.dumps(result,ensure_ascii=False,allow_nan=False))
  except Exception as exc:
   print(json.dumps({'error':str(exc)[:300]},ensure_ascii=False));sys.exit(1)
  finally:db.close()
if __name__=='__main__':main()
