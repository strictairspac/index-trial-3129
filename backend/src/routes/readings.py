from fastapi import APIRouter,Depends,Query
from src.middlewares.auth import current,writer
from src.schemas.business import ReadingInput,CorrectInput,BackfillInput,ReconcileInput
from src.services import readings
from src.controllers.business import ingest_reading,retract_reading,correct_reading,run_backfill,reconcile_hour
router=APIRouter()
@router.get('/readings')
def listing(sensor_id:int=Query(ge=1,le=1000),start_at:str|None=None,end_at:str|None=None,include_retracted:bool=False,u=Depends(current)):
 return readings.list_readings(sensor_id,start_at,end_at,include_retracted)
@router.post('/readings',status_code=201)
def create(data:ReadingInput,u=Depends(writer)):return ingest_reading(data,u)
@router.post('/readings/{reading_id}/retract')
def retracting(reading_id:int,u=Depends(writer)):return retract_reading(reading_id,u)
@router.post('/readings/{reading_id}/correct')
def correcting(reading_id:int,data:CorrectInput,u=Depends(writer)):return correct_reading(reading_id,data,u)
@router.get('/readings/summary')
def summarizing(workload_id:int|None=None,sensor_id:int|None=None,start_at:str|None=None,end_at:str|None=None,u=Depends(current)):
 if workload_id is not None:return readings.summary_for_workload(workload_id)
 return readings.summary(sensor_id,start_at,end_at)
@router.get('/readings/hours')
def hours(sensor_id:int=Query(ge=1,le=1000),start_at:str|None=None,end_at:str|None=None,u=Depends(current)):
 return readings.list_hours(sensor_id,start_at,end_at)
@router.post('/readings/backfill')
def backfilling(data:BackfillInput,u=Depends(writer)):return run_backfill(data,u)
@router.get('/readings/backfill')
def backfill_state(sensor_id:int=Query(ge=1,le=1000),u=Depends(current)):return readings.backfill_status(sensor_id)
@router.post('/readings/reconcile')
def reconciling(data:ReconcileInput,u=Depends(writer)):return reconcile_hour(data,u)
