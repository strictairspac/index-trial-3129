# Schema v2 — 巡检小时汇总
新增三表（SQLAlchemy metadata 自动建表）：

- `readings`：设备读数原始记录。`status` active/retracted 软删除；`(sensor_id, client_ref)` 唯一约束提供录入幂等键，客户端重试不重复计数。
- `reading_hours`：按 `(sensor_id, hour)` 唯一的小时汇总（cnt/min_v/max_v）。`state` pending（未核对，读路径回退原始记录）→ verified（核对一致，读路径走汇总）。
- `backfill_states`：每设备一行回填断点 `next_hour`→`target_hour`。

一致性约定：

1. 原始记录变更与汇总变更在同一事务提交；所有汇总行变更先 `SELECT ... FOR UPDATE` 锁定该小时行（MySQL InnoDB 行锁），跨小时更正按小时排序加锁避免死锁。
2. 录入/跨小时更正的目标小时走增量（cnt±1、min/max 比较）；撤回或更正触及极值时只重算受影响的小时（单小时 `count/min/max` 重算）。
3. 回填按小时整段重算（幂等），逐小时提交并推进断点；中断后从 `next_hour` 续跑，不会重复计数。回填与并发写入靠同一行锁串行化：写入的增量要么落在重算之前（被重算覆盖包含），要么落在重算之后（增量作用于最新汇总）。
4. 读路径只对 verified 小时用汇总；pending 小时与首尾不足一小时的区间实时聚合原始记录。
