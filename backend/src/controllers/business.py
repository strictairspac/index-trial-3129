from src.services import workloads,candidates,experiments,readings
from src.services.audit import log
def save_workload(data,user,item_id=None):
 row=workloads.save(data,item_id);log(user.email,'workload.save',row['name']);return row
def save_candidate(data,user,item_id=None):
 row=candidates.save(data,item_id);log(user.email,'candidate.save',row['name']);return row
def start_experiment(data,user):
 row=experiments.create(data);log(user.email,'experiment.queue',row['name']);return row
def ingest_reading(data,user):
 row=readings.ingest(data);log(user.email,'reading.ingest',f"sensor={row['sensor_id']} at={row['recorded_at']}");return row
def retract_reading(reading_id,user):
 row=readings.retract(reading_id);log(user.email,'reading.retract',f"id={reading_id} changed={row['changed']}");return row
def correct_reading(reading_id,data,user):
 row=readings.correct(reading_id,data);log(user.email,'reading.correct',f"id={reading_id} changed={row['changed']}");return row
def run_backfill(data,user):
 row=readings.backfill(data);log(user.email,'reading.backfill',f"sensor={row['sensor_id']} processed={row['processed']} done={row['done']}");return row
def reconcile_hour(data,user):
 row=readings.reconcile(data);log(user.email,'reading.reconcile',f"sensor={row['sensor_id']} hour={row['hour']} drift={row['drift']}");return row
