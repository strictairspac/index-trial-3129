# 巡检小时汇总验收脚本：撤回并列极值 / 跨小时更正 / 回填续跑（含并发写入与重试幂等）
# 运行：cd backend && python3 /workspace/test-artifacts/gb-4102/run_tests.py
# 使用独立 SQLite 库与 TestClient，不改动任何现有数据；全部时间戳固定，可重复执行。
import os,sys,json,datetime
os.environ.setdefault('DATABASE_URL','sqlite:////tmp/gb4102/readings_acceptance.db')
os.environ.setdefault('JWT_SECRET','gb4102-acceptance-secret')
os.environ.setdefault('SEED_DEMO','true')
os.makedirs('/tmp/gb4102',exist_ok=True)
if os.path.exists('/tmp/gb4102/readings_acceptance.db'):os.remove('/tmp/gb4102/readings_acceptance.db')
sys.path.insert(0,'/workspace/backend')
from fastapi.testclient import TestClient
from sqlalchemy import select
from src.main import app
from src.config.database import Session
from src.models.reading import Reading,ReadingHour

RESULTS=[]
def check(name,cond,detail=''):
 RESULTS.append((name,bool(cond),detail))
 print(('PASS' if cond else 'FAIL'),name,('- '+detail if detail else ''))

def raw_agg(sensor,start,end):
 with Session() as s:
  vals=s.execute(select(Reading.value).where(Reading.sensor_id==sensor,Reading.status=='active',Reading.recorded_at>=start,Reading.recorded_at<end)).scalars().all()
 return (len(vals),min(vals) if vals else None,max(vals) if vals else None)

def hour_row(sensor,hour):
 with Session() as s:
  r=s.execute(select(ReadingHour).where(ReadingHour.sensor_id==sensor,ReadingHour.hour==hour)).scalar_one_or_none()
  return None if r is None else {'cnt':r.cnt,'min_v':r.min_v,'max_v':r.max_v,'state':r.state}

with TestClient(app) as c:
 admin=c.post('/auth/login',json={'email':'admin@index.local','password':'Trial2026!'}).json()['token']
 H={'Authorization':'Bearer '+admin}
 viewer={'Authorization':'Bearer '+c.post('/auth/login',json={'email':'viewer@index.local','password':'Trial2026!'}).json()['token']}
 def ingest(sensor,at,value,ref=None,expect=201):
  r=c.post('/readings',json={'sensor_id':sensor,'recorded_at':at,'value':value,'client_ref':ref},headers=H)
  assert r.status_code==expect,(r.status_code,r.text)
  return r.json()
 def summary(params):
  r=c.get('/readings/summary',params=params,headers=H);assert r.status_code==200,r.text
  return r.json()

 # ---------- S1 撤回并列极值：只重算受影响的小时 ----------
 S=901;D='2026-11-10'
 ids={}
 for tag,at,v in [('a',D+'T08:05:00',10.0),('b',D+'T08:15:00',10.0),('c',D+'T08:25:00',20.0),('d',D+'T08:45:00',30.0),('e',D+'T09:10:00',99.0)]:
  ids[tag]=ingest(S,at,v,'s1-'+tag)['id']
 bf=c.post('/readings/backfill',json={'sensor_id':S,'restart':True,'batch':744},headers=H).json()
 check('S1 回填一次完成',bf['done'] and bf['processed']==2,json.dumps(bf,ensure_ascii=False))
 before={h['hour']:h for h in c.get('/readings/hours',params={'sensor_id':S},headers=H).json()}
 r=c.post(f"/readings/{ids['a']}/retract",headers=H).json()
 check('S1 撤回并列极值之一',r['changed'] is True)
 h8=hour_row(S,D+'T08')
 check('S1 并列最小值撤回一个后 min 仍为10',h8['cnt']==3 and h8['min_v']==10.0 and h8['max_v']==30.0,str(h8))
 after={h['hour']:h for h in c.get('/readings/hours',params={'sensor_id':S},headers=H).json()}
 untouched={k:v for k,v in after.items() if k!=D+'T08'}
 check('S1 未受影响小时保持原样（只重算受影响小时）',all(before[k]==v for k,v in untouched.items()))
 r=c.post(f"/readings/{ids['b']}/retract",headers=H).json()
 h8=hour_row(S,D+'T08')
 check('S1 并列最小值全部撤回后 min 升至20',h8['cnt']==2 and h8['min_v']==20.0 and h8['max_v']==30.0,str(h8))
 cnt,mn,mx=raw_agg(S,D+'T08:00:00',D+'T09:00:00')
 check('S1 汇总与原始记录一致',(h8['cnt'],h8['min_v'],h8['max_v'])==(cnt,mn,mx),f'raw={(cnt,mn,mx)}')
 r=c.post(f"/readings/{ids['b']}/retract",headers=H).json()
 check('S1 重复撤回幂等',r['changed'] is False and hour_row(S,D+'T08')['cnt']==2)
 s=summary({'sensor_id':S,'start_at':D+'T08:00:00','end_at':D+'T10:00:00'})
 check('S1 汇总读总数/极值正确',s['count']==3 and s['min']==20.0 and s['max']==99.0 and all(b['source']=='summary' for b in s['hours']))

 # ---------- S2 跨小时更正 ----------
 S=902;D='2026-11-11'
 a=ingest(S,D+'T10:15:00',5.0,'s2-a')['id'];b=ingest(S,D+'T10:45:00',7.0,'s2-b')['id'];e=ingest(S,D+'T11:10:00',9.0,'s2-c')['id']
 c.post('/readings/backfill',json={'sensor_id':S,'restart':True,'batch':744},headers=H)
 r=c.post(f'/readings/{a}/correct',json={'recorded_at':D+'T11:50:00'},headers=H).json()
 check('S2 跨小时更正已确认',r['changed'] is True and r['recorded_at']==D+'T11:50:00')
 h10,h11=hour_row(S,D+'T10'),hour_row(S,D+'T11')
 check('S2 源小时极值重算',(h10['cnt'],h10['min_v'],h10['max_v'])==(1,7.0,7.0),str(h10))
 check('S2 目标小时增量合并',(h11['cnt'],h11['min_v'],h11['max_v'])==(2,5.0,9.0),str(h11))
 check('S2 两小时后仍保持已核对',h10['state']=='verified' and h11['state']=='verified')
 raw10,raw11=raw_agg(S,D+'T10:00:00',D+'T11:00:00'),raw_agg(S,D+'T11:00:00',D+'T12:00:00')
 check('S2 源/目标小时与原始记录一致',(h10['cnt'],h10['min_v'],h10['max_v'])==raw10 and (h11['cnt'],h11['min_v'],h11['max_v'])==raw11,f'{raw10} {raw11}')
 r=c.post(f'/readings/{e}/correct',json={'value':1.0},headers=H).json()
 h11=hour_row(S,D+'T11')
 check('S2 同小时改值触及极值重算该小时',(h11['cnt'],h11['min_v'],h11['max_v'])==(2,1.0,5.0),str(h11))
 r=c.post(f"/readings/{ids['a']}/correct",json={'value':1.0},headers=H)
 check('S2 已撤回记录不可更正',r.status_code==409)

 # ---------- S3 回填续跑：中断重试不重复计数 + 回填期间并发写入 ----------
 S=903;D='2026-11-12'
 for i in range(10):ingest(S,f'{D}T{i:02d}:10:00',i*1.5,f's3-{i}')
 dup=ingest(S,D+'T03:10:00',4.5,'s3-3')
 check('S3 录入重试按 client_ref 幂等',dup['duplicated'] is True and len(c.get('/readings',params={'sensor_id':S},headers=H).json())==10)
 bf1=c.post('/readings/backfill',json={'sensor_id':S,'restart':True,'batch':4},headers=H).json()
 check('S3 首批回填停在断点',bf1['processed']==4 and bf1['next_hour']==D+'T04' and not bf1['done'],json.dumps(bf1))
 ingest(S,D+'T01:40:00',0.5,'s3-late1')# 并发写入：落入已核对小时
 ingest(S,D+'T07:33:00',100.0,'s3-late2')# 并发写入：落入未追平小时
 bf2=c.post('/readings/backfill',json={'sensor_id':S,'batch':3},headers=H).json()
 bf3=c.post('/readings/backfill',json={'sensor_id':S,'batch':10},headers=H).json()
 check('S3 续跑从断点继续并跑完',bf2['next_hour']==D+'T07' and bf3['done'] and bf1['processed']+bf2['processed']+bf3['processed']==10,f"{bf2['next_hour']} {bf3}")
 drifts=[]
 for i in range(10):
  r=c.post('/readings/reconcile',json={'sensor_id':S,'hour':f'{D}T{i:02d}:00:00'},headers=H).json()
  if r['drift']:drifts.append(r['hour'])
 check('S3 逐小时核对零漂移（无重复计数/无丢失）',not drifts,str(drifts))
 h1,h7=hour_row(S,D+'T01'),hour_row(S,D+'T07')
 check('S3 并发写入已核对小时被保留',(h1['cnt'],h1['min_v'],h1['max_v'])==(2,0.5,1.5),str(h1))
 check('S3 并发写入未追平小时被回填正确吸收',(h7['cnt'],h7['min_v'],h7['max_v'],h7['state'])==(2,10.5,100.0,'verified'),str(h7))
 s=summary({'sensor_id':S,'start_at':D+'T00:00:00','end_at':D+'T10:00:00'})
 cnt,mn,mx=raw_agg(S,D+'T00:00:00',D+'T10:00:00')
 check('S3 汇总读与原始记录一致',(s['count'],s['min'],s['max'])==(cnt,mn,mx)==(12,0.0,100.0),f"summary={(s['count'],s['min'],s['max'])} raw={(cnt,mn,mx)}")
 check('S3 全部小时走汇总读',all(b['source']=='summary' for b in s['hours']))
 bf4=c.post('/readings/backfill',json={'sensor_id':S,'batch':10},headers=H).json()
 check('S3 完成后重复调用不再处理',bf4['processed']==0 and bf4['done'])
 c.post('/readings/backfill',json={'sensor_id':S,'restart':True,'batch':744},headers=H)
 s2=summary({'sensor_id':S,'start_at':D+'T00:00:00','end_at':D+'T10:00:00'})
 check('S3 整体重跑幂等（仍不重复计数）',(s2['count'],s2['min'],s2['max'])==(12,0.0,100.0))

 # ---------- S4 读路由：未追平小时与首尾不足一小时回退原始记录 ----------
 S=904;D='2026-11-15'
 for at,v in [(D+'T08:20:00',1.0),(D+'T08:40:00',2.0),(D+'T09:10:00',3.0),(D+'T10:05:00',4.0),(D+'T10:55:00',5.0)]:ingest(S,at,v)
 c.post('/readings/backfill',json={'sensor_id':S,'start_at':D+'T09:00:00','end_at':D+'T09:59:00','restart':True,'batch':744},headers=H)
 s=summary({'sensor_id':S,'start_at':D+'T08:30:00','end_at':D+'T10:30:00'})
 srcs=[(b.get('hour') or 'partial',b['source'],b['partial']) for b in s['hours']]
 check('S4 首尾不足一小时走原始记录',s['hours'][0]['source']=='raw' and s['hours'][0]['partial'] and s['hours'][-1]['source']=='raw' and s['hours'][-1]['partial'],str(srcs))
 check('S4 已核对小时走汇总、未追平小时走原始记录',s['hours'][1]=={'hour':D+'T09','count':1,'min':3.0,'max':3.0,'source':'summary','partial':False},str(srcs))
 check('S4 混合路径合计正确',(s['count'],s['min'],s['max'])==(3,2.0,4.0),f"{s['count']} {s['min']} {s['max']}")
 s=summary({'sensor_id':S,'start_at':D+'T08:00:00','end_at':D+'T11:00:00'})
 srcs={b['hour']:b['source'] for b in s['hours']}
 check('S4 整点对整点无首尾碎片',srcs=={D+'T08':'raw',D+'T09':'summary',D+'T10':'raw'} and (s['count'],s['min'],s['max'])==(5,1.0,5.0),str(srcs))
 w=c.post('/workloads',json={'name':'巡检核对904','sensor_id':S,'start_at':D+'T08:30:00','end_at':D+'T10:30:00'},headers=H).json()
 s=summary({'workload_id':w['id']})
 check('S4 按现有负载时间范围查询',s['workload_id']==w['id'] and (s['count'],s['min'],s['max'])==(3,2.0,4.0))

 # ---------- S5 核对一致后才切换汇总读 ----------
 S=905;D='2026-11-16'
 ingest(S,D+'T14:05:00',8.0);ingest(S,D+'T14:45:00',6.0)
 s=summary({'sensor_id':S,'start_at':D+'T14:00:00','end_at':D+'T15:00:00'})
 check('S5 未核对小时读原始记录',s['hours'][0]['source']=='raw' and s['count']==2)
 r=c.post('/readings/reconcile',json={'sensor_id':S,'hour':D+'T14:00:00'},headers=H).json()
 check('S5 核对一致',r['drift'] is False and r['state']=='verified',json.dumps(r))
 s=summary({'sensor_id':S,'start_at':D+'T14:00:00','end_at':D+'T15:00:00'})
 check('S5 核对后切换汇总读',s['hours'][0]=={'hour':D+'T14','count':2,'min':6.0,'max':8.0,'source':'summary','partial':False})
 with Session() as ss:
  row=ss.execute(select(ReadingHour).where(ReadingHour.sensor_id==S,ReadingHour.hour==D+'T14')).scalar_one();row.cnt=999;ss.commit()
 r=c.post('/readings/reconcile',json={'sensor_id':S,'hour':D+'T14:00:00'},headers=H).json()
 check('S5 核对能发现漂移并以原始记录为准修复',r['drift'] is True and r['before']['cnt']==999 and r['after']['cnt']==2,json.dumps(r))

 # ---------- S6 边界与权限 ----------
 r=summary({'sensor_id':906,'start_at':'2026-11-17T00:00:00','end_at':'2026-11-17T02:00:00'})
 check('S6 空区间返回零计数与空极值',r['count']==0 and r['min'] is None and r['max'] is None and len(r['hours'])==2)
 r=c.post('/readings',content='{"sensor_id":906,"recorded_at":"2026-11-17T00:10:00","value":NaN}',headers={**H,'Content-Type':'application/json'})
 check('S6 非有限读数被拒绝',r.status_code==422)
 r=c.post('/readings',json={'sensor_id':906,'recorded_at':'bad','value':1.0},headers=H)
 check('S6 非法时间被拒绝',r.status_code==422)
 r=c.post('/readings',json={'sensor_id':906,'recorded_at':'2026-11-17T00:10:00','value':1.0},headers=viewer)
 check('S6 观察员写请求被拒',r.status_code==403)
 r=c.get('/readings/summary',params={'sensor_id':906},headers=H)
 check('S6 缺少时间范围返回422',r.status_code==422)

passed=sum(1 for _,ok,_ in RESULTS if ok);total=len(RESULTS)
lines=['# gb-4102 巡检小时汇总验收报告','',f"日期：{datetime.date.today().isoformat()}  结果：{passed}/{total} 通过",'',
 '| 用例 | 结果 | 说明 |','|---|---|---|']
lines+=['| {} | {} | {} |'.format(n,'✅' if ok else '❌',d.replace('|','/')) for n,ok,d in RESULTS]
lines+=['','环境：FastAPI TestClient + SQLite（行锁语义在 MySQL InnoDB 下由 SELECT ... FOR UPDATE 保证，见 backend/migrations/002_readings.md）。']
open('/workspace/test-artifacts/gb-4102/report.md','w').write('\n'.join(lines)+'\n')
print(f'\n{passed}/{total} passed -> test-artifacts/gb-4102/report.md')
sys.exit(0 if passed==total else 1)
