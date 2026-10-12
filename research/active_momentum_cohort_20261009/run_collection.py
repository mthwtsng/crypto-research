"""Single-supervisor, resumable six-process collection; writes only here."""
import sys
sys.dont_write_bytecode=True
import datetime,fcntl,hashlib,json,os,pathlib,subprocess,time
P=pathlib.Path(__file__).resolve().parent
# The child owns RUN.lock; this separate lease prevents duplicate supervisors.
lock=(P/'SUPERVISOR.lock').open('a+')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
env.setdefault('COHORT_ALCHEMY_CU_PER_SECOND','400')
env.setdefault('COHORT_HELIUS_TARGET_RPS','15')
env.setdefault('COHORT_HELIUS_MAX_IN_FLIGHT','8')
env.setdefault('COHORT_HELIUS_2_TARGET_RPS','15')
env.setdefault('COHORT_HELIUS_2_MAX_IN_FLIGHT','8')
rpc_source_sha256=hashlib.sha256((P/'rpc_pool.py').read_bytes()).hexdigest()
def status(value):
 path=P/'SUPERVISOR.json';tmp=path.with_name(path.name+'.'+str(os.getpid())+'.partial')
 tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)
num_workers=int(os.environ.get('COHORT_WORKERS','16'))
code=1
for attempt in range(1,4):
 status(dict(state='running',mode='parallel',workers=num_workers,attempt=attempt,rpc_source_sha256=rpc_source_sha256,alchemy_local_cu_per_second=float(env['COHORT_ALCHEMY_CU_PER_SECOND']),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
 with (P/'PARALLEL_COLLECTION.log').open('a') as log:
  log.write('\nPARALLEL SUPERVISOR ATTEMPT '+str(attempt)+'\n');log.flush()
  code=subprocess.call([sys.executable,str(P/'parallel_collect.py'),'--workers',str(num_workers)],stdout=log,stderr=log,env=env)
 if (P/'COLLECTION_COMPLETE.json').exists():break
 coordinator={}
 if (P/'PARALLEL_STATUS.json').exists():
  with (P/'PARALLEL_STATUS.json').open() as f:coordinator=json.load(f)
 if code==0 and coordinator.get('state')=='complete':break
 if coordinator.get('state')=='candidate_pool_exhausted':break
 if attempt<3:time.sleep(20)
state='complete' if (P/'COLLECTION_COMPLETE.json').exists() else 'stopped_incomplete'
status(dict(state=state,mode='parallel',workers=num_workers,attempt=attempt,exit_code=code,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
sys.exit(0 if state=='complete' else (code or 1))
