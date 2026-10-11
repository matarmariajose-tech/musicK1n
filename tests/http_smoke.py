"""Run against an isolated local server only; never against production."""
import base64,json,urllib.request,urllib.error,subprocess,time
base='http://127.0.0.1:3108';auth='Basic '+base64.b64encode(b'test-operator:local-test-password').decode()
def req(path,data=None,headers=None):
 h={'Authorization':auth};h.update(headers or {})
 r=urllib.request.urlopen(urllib.request.Request(base+path,data=data,headers=h),timeout=10);return r.status,r.read()
assert req('/eve/v1/health')[0]==200
try:urllib.request.urlopen(base+'/')
except urllib.error.HTTPError as e:assert e.code==401
else:raise AssertionError('unauthorized access')
assert b'Growth Studio' in req('/')[1]
try:req('/api/action',b'{"action":"report"}',{'Content-Type':'application/json','Origin':'https://evil.example'})
except urllib.error.HTTPError as e:assert e.code==403
else:raise AssertionError('cross origin accepted')
audio=subprocess.check_output(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=7','-f','wav','pipe:1'])
asset=json.loads(req('/api/upload',audio,{'X-Asset-Kind':'audio','X-File-Name':'test.wav'})[1])
def action(name,payload):return json.loads(req('/api/action',json.dumps({'action':name,'payload':payload}).encode(),{'Content-Type':'application/json'})[1])
t=action('track',{'title':'HTTP test','audio':asset['id']})
e=action('experiment',{'track_id':t['id'],'start':0,'end':6,'style':'waveform','title':'HTTP clip','destination':'https://www.youtube.com/watch?v=my4E2FRFuH8'})
action('render',{'id':e['id']})
for _ in range(30):
 overview=json.loads(req('/api/overview')[1]);exp=next(x for x in overview['experiments'] if x['id']==e['id'])
 if exp['status']=='rendered':break
 time.sleep(.3)
assert exp['status']=='rendered',overview['jobs']
assert req('/media/'+e['id'])[0]==200
action('approve',{'id':e['id']})
try:action('upload-private',{'id':e['id'],'confirm':'UPLOAD_PRIVATE'})
except urllib.error.HTTPError as x:assert x.code==400
else:raise AssertionError('upload without credentials accepted')
print('PASS: health, auth, dashboard, CSRF, upload, experiment, background render, video, approval, credential gate')
