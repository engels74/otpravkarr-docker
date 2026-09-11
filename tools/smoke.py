#!/usr/bin/env python3
import hashlib,json,os,secrets,subprocess,sys,time,uuid,tempfile
from pathlib import Path
tooling=Path(__file__).resolve().parent
image=sys.argv[1];r=Path(sys.argv[2]).resolve();r.mkdir(parents=True,exist_ok=True);arch=sys.argv[3]
metadata=json.loads((r/'metadata.json').read_text())
expected_version=next(v.split('=',1)[1] for v in metadata['build_args'] if v.startswith('VERSION='))
suffix=uuid.uuid4().hex[:8];name='otpravkarr-validation-'+arch+'-'+suffix;volume=name;network=name+'-network'
secret=secrets.token_urlsafe(48);secret_file=Path(tempfile.mkdtemp(prefix=name+'-'))/'secret.env';secret_file.write_text('OTPRAVKARR_SECRET='+secret+'\n');secret_file.chmod(0o600)
result={'architecture':arch,'volume':volume,'checks':[]}
def docker(*args,check=True,env=None):
 p=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=90,env=env)
 if check and p.returncode:raise RuntimeError('docker '+args[0]+' failed: '+p.stderr[:1000])
 return (p.stdout + p.stderr if args[0] == "logs" else p.stdout).strip()
def js(code):return json.loads(docker('exec',name,'bun','-e',code))
def ready():
 for _ in range(45):
  try:
   v=js("const r=await fetch('http://127.0.0.1:4321/api/health',{signal:AbortSignal.timeout(1000)});console.log(JSON.stringify({code:r.status,body:await r.json()}))")
   if v['code']==200 and v['body']=={'status':'degraded'}:return v
  except Exception:pass
  time.sleep(1)
 raise RuntimeError('readiness failed')
def save_log(suffix):
 p=r/(name+'-'+suffix+'.log');p.write_text(docker('logs',name,check=False));p.chmod(0o600)
def stop():
 start=time.monotonic();docker('stop','--time','15',name);state=json.loads(docker('inspect',name))[0]['State'];elapsed=time.monotonic()-start
 assert state['ExitCode']==0 and not state['OOMKilled'] and elapsed<15,state
 return round(elapsed,3)
def start(extra=()):
 docker('run','-d','--name',name,'--network',network,'--env-file',str(secret_file),'-e','PUID=12345','-e','PGID=12345','-e','PORT=4321','-e','TZ=UTC','-v',volume+':/config',*extra,image)
def crypto(mode):
 docker('cp',str(tooling/'crypto-probe.mjs'),name+':/tmp/crypto-probe.mjs')
 env=os.environ.copy()
 if mode=='wrong':env['OTPRAVKARR_SECRET']=secrets.token_urlsafe(48)
 args=['exec','-w','/app']
 if mode=='wrong':args+=['-e','OTPRAVKARR_SECRET']
 args += [name,'bun','/tmp/crypto-probe.mjs',mode]
 value=json.loads(docker(*args,env=env).splitlines()[-1]);return value
try:
 docker('network','create','--internal',network)
 # Negative cases use no persistent volume and never print the disposable secret.
 for label,value in [('missing',None),('short','short'),('weak','a'*64)]:
  args=['run','-d','--name',name,'--network',network,'-e','PORT=4321']
  env=os.environ.copy()
  if value is not None:env['OTPRAVKARR_SECRET']=value;args+=['-e','OTPRAVKARR_SECRET']
  docker(*args,image,env=env)
  for _ in range(20):
   state=json.loads(docker('inspect',name))[0]['State']
   if not state['Running']:break
   # Environment validation in the app happens on its first request.
   docker('exec',name,'curl','--max-time','1','-s','http://127.0.0.1:4321/api/health',check=False)
   time.sleep(.25)
  logs=docker('logs',name,check=False);save_log(label)
  assert 'OTPRAVKARR_SECRET' in logs
  no_listener=docker('exec',name,'curl','--max-time','1','-s','http://127.0.0.1:4321/api/health',check=False)==''
  assert no_listener
  if label in {'missing','short'}: assert not state['Running'] and state['ExitCode']==1,state
  result['checks'].append({label+'_secret_rejected':True,'exited':not state['Running'],'exit':state['ExitCode']})
  docker('stop','--time','2',name,check=False);docker('rm','-v',name)
 docker('volume','create',volume)
 start();result['checks'].append({'fresh':ready()})
 page=js("const r=await fetch('http://127.0.0.1:4321/setup');const body=await r.text();console.log(JSON.stringify({code:r.status,app:body.toLowerCase().includes('otpravkarr')}))");assert page=={'code':200,'app':True}
 info=js("import {readdirSync,readFileSync,statSync,realpathSync} from 'node:fs';const app=readdirSync('/proc').filter(p=>/^\\d+$/.test(p)).map(p=>{try{return{pid:p,cmd:readFileSync('/proc/'+p+'/cmdline','utf8').split('\\0'),status:readFileSync('/proc/'+p+'/status','utf8')}}catch{return null}}).find(p=>p&&p.cmd.length===3&&p.cmd[0]==='bun'&&p.cmd[1]==='./build/index.js');const st=statSync('/config/data/otpravkarr.sqlite');console.log(JSON.stringify({bun:Bun.version,arch:process.arch,production:process.env.NODE_ENV,data:realpathSync('/app/data'),uid:st.uid,gid:st.gid,appUid:app?.status.match(/Uid:\\s+(\\d+)/)[1]}))")
 assert info=={'bun':'1.4.2','arch':{'amd64':'x64','arm64':'arm64'}[arch],'production':'production','data':'/config/data','uid':12345,'gid':12345,'appUid':'12345'},info
 expected=json.loads((tooling/'migration-checksums.json').read_text())
 assert js("console.log(JSON.stringify(process.env.COMMIT_TAG))")==expected_version
 (r/'packages.txt').write_text(docker('exec',name,'apk','info','-v')+'\n')
 actual=js("import {readdirSync} from 'node:fs';const dir='/app/build/server/migrations/';const hashes={};for(const f of readdirSync(dir).filter(n=>n.endsWith('.sql'))){hashes[f]=new Bun.CryptoHasher('sha256').update(await Bun.file(dir+f).arrayBuffer()).digest('hex')}console.log(JSON.stringify(hashes))")
 assert expected==actual
 initial=crypto('write');assert initial['migrations']==len(expected),initial
 result['checks'].append({'runtime':info,'migration_bytes':True,'crypto':initial,'wrong_key':crypto('wrong')})
 result['checks'].append({'first_stop_seconds':stop()});save_log('first')
 docker('start',name);result['checks'].append({'restart':ready(),'crypto':crypto('read'),'stop_seconds':stop()});save_log('restart')
 docker('cp',name+':/config/data',str(r/(name+'-backup')));docker('rm',name)
 start();result['checks'].append({'replacement':ready(),'crypto':crypto('read'),'stop_seconds':stop()});save_log('replacement');docker('rm',name)
 # Existing configuration volume, but a nonexistent explicit database must not be recreated.
 start(('-e','DATABASE_PATH=/config/data/missing-configured.sqlite'))
 response=None
 for _ in range(30):
  try:
   response=js("const r=await fetch('http://127.0.0.1:4321/api/health');console.log(JSON.stringify({code:r.status}))")
   break
  except Exception:time.sleep(.25)
 assert response=={'code':500},response
 missing=js("console.log(JSON.stringify({exists:await Bun.file('/config/data/missing-configured.sqlite').exists()}))")
 assert missing=={'exists':False};result['checks'].append({'missing_configured_database_rejected':True,'stop_seconds':stop()});save_log('missing-database')
 result['passed']=True
 (r/'result.txt').write_text('PASS: native setup/version/migrations/secrets/encrypted persistence/database guard/clean shutdown\n')
finally:
 docker('stop','--time','15',name,check=False);docker('rm',name,check=False);docker('network','rm',network,check=False)
 (r/'runtime-result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
