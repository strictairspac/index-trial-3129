from pydantic import BaseModel,Field,model_validator
from datetime import datetime
import math
from src.constants.enums import COLUMNS
def _naive(ts):
 a=datetime.fromisoformat(ts)
 return a.replace(tzinfo=None).isoformat(timespec='seconds')
class Login(BaseModel):
 email:str;password:str
class WorkloadInput(BaseModel):
 name:str=Field(min_length=2,max_length=120)
 sensor_id:int=Field(ge=1,le=1000)
 start_at:str='2026-11-01T00:00:00'
 end_at:str='2026-11-30T23:59:59'
 device_type:str|None=None
 description:str=Field(default='',max_length=500)
 @model_validator(mode='after')
 def valid_dates(self):
  a=datetime.fromisoformat(self.start_at);b=datetime.fromisoformat(self.end_at)
  if a>=b:raise ValueError('结束时间必须晚于开始时间')
  if self.device_type not in (None,'pump','motor','valve'):raise ValueError('设备类型无效')
  self.start_at=a.isoformat(timespec='seconds');self.end_at=b.isoformat(timespec='seconds')
  return self
class CandidateInput(BaseModel):
 name:str=Field(min_length=2,max_length=120)
 workload_id:int
 columns:list[str]=Field(min_length=1,max_length=4)
 note:str=Field(default='',max_length=500)
 @model_validator(mode='after')
 def columns_valid(self):
  if len(set(self.columns))!=len(self.columns) or any(x not in COLUMNS for x in self.columns):raise ValueError('索引列必须唯一且来自白名单')
  return self
class ExperimentInput(BaseModel):
 name:str=Field(min_length=2,max_length=120)
 candidate_id:int
class ReadingInput(BaseModel):
 sensor_id:int=Field(ge=1,le=1000)
 recorded_at:str
 value:float
 client_ref:str|None=Field(default=None,max_length=64)
 @model_validator(mode='after')
 def valid(self):
  self.recorded_at=_naive(self.recorded_at)
  if not math.isfinite(self.value):raise ValueError('读数必须是有限数值')
  return self
class CorrectInput(BaseModel):
 recorded_at:str|None=None
 value:float|None=None
 @model_validator(mode='after')
 def valid(self):
  if self.recorded_at is None and self.value is None:raise ValueError('至少更正时间或读数之一')
  if self.recorded_at is not None:self.recorded_at=_naive(self.recorded_at)
  if self.value is not None and not math.isfinite(self.value):raise ValueError('读数必须是有限数值')
  return self
class BackfillInput(BaseModel):
 sensor_id:int=Field(ge=1,le=1000)
 start_at:str|None=None
 end_at:str|None=None
 batch:int=Field(default=24,ge=1,le=744)
 restart:bool=False
 @model_validator(mode='after')
 def valid(self):
  if self.start_at is not None:self.start_at=_naive(self.start_at)
  if self.end_at is not None:self.end_at=_naive(self.end_at)
  if self.start_at and self.end_at and self.start_at>=self.end_at:raise ValueError('结束时间必须晚于开始时间')
  return self
class ReconcileInput(BaseModel):
 sensor_id:int=Field(ge=1,le=1000)
 hour:str
 @model_validator(mode='after')
 def valid(self):
  self.hour=_naive(self.hour)
  return self
