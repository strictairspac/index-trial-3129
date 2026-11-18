from datetime import datetime,timedelta
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from src.config.database import Session
from src.models.reading import Reading,ReadingHour,BackfillState
from src.models.workload import Workload
from src.utils.serialization import record
# 一致性约定：所有汇总变更（增量或重算）都在同一事务内先锁定 reading_hours 行，
# 原始记录变更与汇总变更同事务提交；回填按小时重算并逐小时提交断点，重试幂等。
def hour_of(ts):return ts[:13]
def hour_plus(h,n=1):return (datetime.strptime(h,'%Y-%m-%dT%H')+timedelta(hours=n)).strftime('%Y-%m-%dT%H')
def hour_start(h):return h+':00:00'
def _hour_row(s,sensor,hour,lock=False):
 q=select(ReadingHour).where(ReadingHour.sensor_id==sensor,ReadingHour.hour==hour)
 if lock:q=q.with_for_update()
 return s.execute(q).scalar_one_or_none()
def _ensure_hour(s,sensor,hour):
 row=_hour_row(s,sensor,hour,lock=True)
 if row:return row
 try:
  with s.begin_nested():
   row=ReadingHour(sensor_id=sensor,hour=hour,cnt=0,state='pending');s.add(row);s.flush()
 except IntegrityError:pass# 并发已建，重新加锁读取
 return _hour_row(s,sensor,hour,lock=True)
def _aggregate(s,sensor,start,end):
 return s.execute(select(func.count(),func.min(Reading.value),func.max(Reading.value)).where(Reading.sensor_id==sensor,Reading.status=='active',Reading.recorded_at>=start,Reading.recorded_at<end)).one()
def _recompute(s,row):
 row.cnt,row.min_v,row.max_v=_aggregate(s,row.sensor_id,row.hour,hour_plus(row.hour))
def _apply_insert(s,sensor,hour,value):
 row=_ensure_hour(s,sensor,hour)
 row.cnt+=1
 row.min_v=value if row.min_v is None else min(row.min_v,value)
 row.max_v=value if row.max_v is None else max(row.max_v,value)
def _apply_remove(s,sensor,hour,value):
 row=_ensure_hour(s,sensor,hour)
 if row.cnt<=0:_recompute(s,row);return# 防御：汇总缺失时以原始记录为准重算该小时
 row.cnt-=1
 if value<=row.min_v or value>=row.max_v:_recompute(s,row)# 撤掉极值只重算受影响的小时
 elif row.cnt==0:row.min_v=None;row.max_v=None
def ingest(data):
 with Session() as s:
  if data.client_ref:
   dup=s.execute(select(Reading).where(Reading.sensor_id==data.sensor_id,Reading.client_ref==data.client_ref)).scalar_one_or_none()
   if dup:return record(dup)|{'duplicated':True}
  r=Reading(sensor_id=data.sensor_id,recorded_at=data.recorded_at,value=data.value,client_ref=data.client_ref)
  s.add(r);s.flush()
  _apply_insert(s,r.sensor_id,hour_of(r.recorded_at),r.value)
  s.commit();s.refresh(r);return record(r)|{'duplicated':False}
def retract(reading_id):
 with Session() as s:
  r=s.get(Reading,reading_id)
  if not r:raise HTTPException(404,'未找到读数')
  if r.status=='retracted':return record(r)|{'changed':False}# 撤回幂等
  r.status='retracted';s.flush()
  _apply_remove(s,r.sensor_id,hour_of(r.recorded_at),r.value)
  s.commit();s.refresh(r);return record(r)|{'changed':True}
def correct(reading_id,data):
 with Session() as s:
  r=s.get(Reading,reading_id)
  if not r:raise HTTPException(404,'未找到读数')
  if r.status!='active':raise HTTPException(409,'已撤回的读数不能更正，请重新录入')
  new_at=data.recorded_at or r.recorded_at
  new_val=data.value if data.value is not None else r.value
  old_at,old_val=r.recorded_at,r.value
  oh,nh=hour_of(old_at),hour_of(new_at)
  if oh==nh and new_val==old_val:return record(r)|{'changed':False}
  for h in sorted({oh,nh}):_ensure_hour(s,r.sensor_id,h)# 多行按小时排序加锁，避免死锁
  r.recorded_at,r.value=new_at,new_val;s.flush()
  if oh==nh:
   row=_hour_row(s,r.sensor_id,oh,lock=True)
   if old_val<=row.min_v or old_val>=row.max_v or new_val<=row.min_v or new_val>=row.max_v:_recompute(s,row)
  else:
   _apply_remove(s,r.sensor_id,oh,old_val)# 原始记录已移动，两个受影响小时各自修正
   _apply_insert(s,r.sensor_id,nh,new_val)
  s.commit();s.refresh(r);return record(r)|{'changed':True}
def backfill(data):
 with Session() as s:
  st=s.get(BackfillState,data.sensor_id)
  if data.restart or not st:
   start=hour_of(data.start_at) if data.start_at else None
   if not start:
    first=s.execute(select(func.min(Reading.recorded_at)).where(Reading.sensor_id==data.sensor_id)).scalar()
    if not first:raise HTTPException(409,'该设备暂无读数，无需回填')
    start=hour_of(first)
   if data.end_at:target=hour_plus(hour_of(data.end_at))
   else:
    last=s.execute(select(func.max(Reading.recorded_at)).where(Reading.sensor_id==data.sensor_id)).scalar()
    target=hour_plus(hour_of(last)) if last else start
   if st:st.next_hour,st.target_hour=start,target
   else:st=BackfillState(sensor_id=data.sensor_id,next_hour=start,target_hour=target);s.add(st)
   s.flush()
  processed=0
  while st.next_hour<st.target_hour and processed<data.batch:
   row=_ensure_hour(s,data.sensor_id,st.next_hour)
   _recompute(s,row);row.state='verified'# 重算即核对，一致后该小时切换到汇总读
   st.next_hour=hour_plus(st.next_hour);processed+=1
   s.commit()# 逐小时提交断点，中断后从 next_hour 续跑，重算幂等不重复计数
  return {'sensor_id':data.sensor_id,'next_hour':st.next_hour,'target_hour':st.target_hour,'processed':processed,'done':st.next_hour>=st.target_hour}
def backfill_status(sensor_id):
 with Session() as s:
  st=s.get(BackfillState,sensor_id)
  if not st:return {'sensor_id':sensor_id,'started':False}
  return {'sensor_id':sensor_id,'started':True,'next_hour':st.next_hour,'target_hour':st.target_hour,'done':st.next_hour>=st.target_hour}
def reconcile(data):
 with Session() as s:
  hour=hour_of(data.hour)
  row=_ensure_hour(s,data.sensor_id,hour)
  before={'cnt':row.cnt,'min_v':row.min_v,'max_v':row.max_v}
  c,mn,mx=_aggregate(s,data.sensor_id,hour,hour_plus(hour))
  drift=(c,mn,mx)!=(row.cnt,row.min_v,row.max_v)
  row.cnt,row.min_v,row.max_v=c,mn,mx
  row.state='verified';s.commit()
  return {'sensor_id':data.sensor_id,'hour':hour,'drift':drift,'before':before,'after':{'cnt':c,'min_v':mn,'max_v':mx},'state':'verified'}
def list_readings(sensor_id,start=None,end=None,include_retracted=False,limit=500):
 with Session() as s:
  q=select(Reading).where(Reading.sensor_id==sensor_id)
  if start:q=q.where(Reading.recorded_at>=_norm(start))
  if end:q=q.where(Reading.recorded_at<_norm(end))
  if not include_retracted:q=q.where(Reading.status=='active')
  return [record(r) for r in s.execute(q.order_by(Reading.recorded_at,Reading.id).limit(limit)).scalars()]
def list_hours(sensor_id,start=None,end=None):
 with Session() as s:
  q=select(ReadingHour).where(ReadingHour.sensor_id==sensor_id)
  if start:q=q.where(ReadingHour.hour>=hour_of(_norm(start)))
  if end:q=q.where(ReadingHour.hour<hour_of(_norm(end)))
  return [record(r) for r in s.execute(q.order_by(ReadingHour.hour)).scalars()]
def _raw_block(s,sensor,start,end,partial):
 c,mn,mx=_aggregate(s,sensor,start,end)
 return {'from':start,'to':end,'count':c,'min':mn,'max':mx,'source':'raw','partial':partial}
def _norm(ts):
 try:return datetime.fromisoformat(ts).replace(tzinfo=None).isoformat(timespec='seconds')
 except (TypeError,ValueError):raise HTTPException(422,'时间格式无效，应为 ISO 日期时间')
def summary(sensor,start,end):
 # 已核对小时读汇总；未追平小时与首尾不足一小时的区间读原始记录
 if sensor is None or not start or not end:raise HTTPException(422,'请提供 workload_id 或 sensor_id+start_at+end_at')
 start,end=_norm(start),_norm(end)
 if start>=end:raise HTTPException(422,'结束时间必须晚于开始时间')
 with Session() as s:
  first_full=hour_of(start) if start[14:]=='00:00' else hour_plus(hour_of(start))
  last_full=hour_of(end) if end[14:]=='00:00' else hour_of(end)
  blocks=[]
  if first_full>=last_full:blocks.append(_raw_block(s,sensor,start,end,True))
  else:
   if start<hour_start(first_full):blocks.append(_raw_block(s,sensor,start,hour_start(first_full),True))
   h=first_full
   while h<last_full:
    row=_hour_row(s,sensor,h)
    if row and row.state=='verified':blocks.append({'hour':h,'count':row.cnt,'min':row.min_v,'max':row.max_v,'source':'summary','partial':False})
    else:
     b=_raw_block(s,sensor,hour_start(h),hour_start(hour_plus(h)),False);blocks.append({'hour':h,'count':b['count'],'min':b['min'],'max':b['max'],'source':'raw','partial':False})
    h=hour_plus(h)
   if hour_start(last_full)<end:blocks.append(_raw_block(s,sensor,hour_start(last_full),end,True))
  total=sum(b['count'] for b in blocks)
  vals=[b for b in blocks if b['count']]
  return {'sensor_id':sensor,'start_at':start,'end_at':end,'count':total,'min':min((b['min'] for b in vals),default=None),'max':max((b['max'] for b in vals),default=None),'hours':blocks}
def summary_for_workload(workload_id):
 with Session() as s:
  w=s.get(Workload,workload_id)
  if not w:raise HTTPException(404,'未找到负载')
  sensor,start,end=w.sensor_id,w.start_at,w.end_at
 return summary(sensor,start,end)|{'workload_id':workload_id}
