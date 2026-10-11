import json, os, tempfile, unittest, sys, subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'core'))
import engine

class Flow(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();engine.DATA=Path(self.temp.name);self.db=engine.database()
  self.audio='a'*32;u=engine.DATA/'uploads';u.mkdir()
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=8','-f','wav',str(u/self.audio)],check=True)
  with self.db:
   engine.dispatch(self.db,'asset',{'id':self.audio,'kind':'audio','name':'test.wav'})
  with self.db:
   self.track=engine.dispatch(self.db,'track',{'title':'Real track','audio':self.audio})['id']
 def tearDown(self):self.db.close();self.temp.cleanup()
 def create(self,start=0,end=6):
  with self.db:return engine.dispatch(self.db,'experiment',{'track_id':self.track,'start':start,'end':end,'style':'waveform','destination':'https://www.youtube.com/watch?v=my4E2FRFuH8','title':'Test'})['id']
 def test_render_approval_and_metrics(self):
  ident=self.create()
  with self.db:engine.dispatch(self.db,'render',{'id':ident})
  self.assertTrue(engine.worker_once())
  self.assertTrue((engine.DATA/'clips'/(ident+'.mp4')).exists())
  with self.db:engine.dispatch(self.db,'approve',{'id':ident})
  with self.db:engine.dispatch(self.db,'published',{'id':ident,'video_id':'abcdefghijk'})
  csv='experiment_id,platform,window_start,window_end,views,watch_seconds,subscribers\n'+ident+',youtube,2026-10-01,2026-10-08,200,600,3\n'
  with self.db:engine.dispatch(self.db,'metrics',{'csv':csv})
  with self.db:engine.dispatch(self.db,'metrics',{'csv':csv})
  r=engine.dispatch(self.db,'report',{})['results'];self.assertEqual(len(r),1);self.assertEqual(r[0]['avg_watch_seconds'],3)
  meta=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(engine.DATA/'clips'/(ident+'.mp4'))]))
  video=next(s for s in meta['streams'] if s['codec_type']=='video');self.assertEqual((video['width'],video['height']),(720,1280))
 def test_bounds_deduplication_and_transitions(self):
  with self.assertRaises(ValueError):self.create(0,20)
  ident=self.create();self.assertEqual(ident,self.create())
  with self.assertRaises(ValueError):engine.dispatch(self.db,'approve',{'id':ident})
  with self.db:engine.dispatch(self.db,'render',{'id':ident});again=engine.dispatch(self.db,'render',{'id':ident})
  self.assertFalse(again['queued'])
 def test_metric_transaction_rolls_back(self):
  ident=self.create();csv='experiment_id,platform,window_start,window_end,views,watch_seconds,subscribers\n'+ident+',youtube,2026-10-01,2026-10-08,20,40,0\n'+ident+',youtube,2026-10-01,2026-10-09,-1,10,0\n'
  with self.assertRaises(ValueError):
   with self.db:engine.dispatch(self.db,'metrics',{'csv':csv})
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM metrics').fetchone()[0],0)
 def test_path_traversal_and_missing_secret(self):
  with self.assertRaises(ValueError):engine.asset_path('../catalog.json')
  with self.assertRaises(ValueError):engine.dispatch(self.db,'spotify-sync',{})
 def test_missing_track_rejects(self):
  with self.assertRaises(ValueError):engine.dispatch(self.db,'experiment',{'track_id':'missing','start':0,'end':6})

if __name__=='__main__':unittest.main()
