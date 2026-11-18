from sqlalchemy import Column,Integer,String,Float,UniqueConstraint
from src.config.database import Base
class Reading(Base):
 __tablename__='readings'
 id=Column(Integer,primary_key=True)
 sensor_id=Column(Integer,nullable=False,index=True)
 recorded_at=Column(String(30),nullable=False)
 value=Column(Float,nullable=False)
 status=Column(String(10),nullable=False,default='active')# active | retracted
 client_ref=Column(String(64),nullable=True)# 客户端幂等键，重试不重复计数
 __table_args__=(UniqueConstraint('sensor_id','client_ref',name='uq_reading_ref'),)
class ReadingHour(Base):
 __tablename__='reading_hours'
 id=Column(Integer,primary_key=True)
 sensor_id=Column(Integer,nullable=False)
 hour=Column(String(13),nullable=False)# 形如 2026-11-01T08
 cnt=Column(Integer,nullable=False,default=0)
 min_v=Column(Float,nullable=True)
 max_v=Column(Float,nullable=True)
 state=Column(String(10),nullable=False,default='pending')# pending 未核对 | verified 已核对
 __table_args__=(UniqueConstraint('sensor_id','hour',name='uq_reading_hour'),)
class BackfillState(Base):
 __tablename__='backfill_states'
 sensor_id=Column(Integer,primary_key=True)
 next_hour=Column(String(13),nullable=False)# 下一个待回填小时，即断点
 target_hour=Column(String(13),nullable=False)# 回填终点（不含）
