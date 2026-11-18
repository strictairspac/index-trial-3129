# gb-4102 巡检小时汇总验收报告

日期：2026-11-18  结果：39/39 通过

| 用例 | 结果 | 说明 |
|---|---|---|
| S1 回填一次完成 | ✅ | {"sensor_id": 901, "next_hour": "2026-11-10T10", "target_hour": "2026-11-10T10", "processed": 2, "done": true} |
| S1 撤回并列极值之一 | ✅ |  |
| S1 并列最小值撤回一个后 min 仍为10 | ✅ | {'cnt': 3, 'min_v': 10.0, 'max_v': 30.0, 'state': 'verified'} |
| S1 未受影响小时保持原样（只重算受影响小时） | ✅ |  |
| S1 并列最小值全部撤回后 min 升至20 | ✅ | {'cnt': 2, 'min_v': 20.0, 'max_v': 30.0, 'state': 'verified'} |
| S1 汇总与原始记录一致 | ✅ | raw=(2, 20.0, 30.0) |
| S1 重复撤回幂等 | ✅ |  |
| S1 汇总读总数/极值正确 | ✅ |  |
| S2 跨小时更正已确认 | ✅ |  |
| S2 源小时极值重算 | ✅ | {'cnt': 1, 'min_v': 7.0, 'max_v': 7.0, 'state': 'verified'} |
| S2 目标小时增量合并 | ✅ | {'cnt': 2, 'min_v': 5.0, 'max_v': 9.0, 'state': 'verified'} |
| S2 两小时后仍保持已核对 | ✅ |  |
| S2 源/目标小时与原始记录一致 | ✅ | (1, 7.0, 7.0) (2, 5.0, 9.0) |
| S2 同小时改值触及极值重算该小时 | ✅ | {'cnt': 2, 'min_v': 1.0, 'max_v': 5.0, 'state': 'verified'} |
| S2 已撤回记录不可更正 | ✅ |  |
| S3 录入重试按 client_ref 幂等 | ✅ |  |
| S3 首批回填停在断点 | ✅ | {"sensor_id": 903, "next_hour": "2026-11-12T04", "target_hour": "2026-11-12T10", "processed": 4, "done": false} |
| S3 续跑从断点继续并跑完 | ✅ | 2026-11-12T07 {'sensor_id': 903, 'next_hour': '2026-11-12T10', 'target_hour': '2026-11-12T10', 'processed': 3, 'done': True} |
| S3 逐小时核对零漂移（无重复计数/无丢失） | ✅ | [] |
| S3 并发写入已核对小时被保留 | ✅ | {'cnt': 2, 'min_v': 0.5, 'max_v': 1.5, 'state': 'verified'} |
| S3 并发写入未追平小时被回填正确吸收 | ✅ | {'cnt': 2, 'min_v': 10.5, 'max_v': 100.0, 'state': 'verified'} |
| S3 汇总读与原始记录一致 | ✅ | summary=(12, 0.0, 100.0) raw=(12, 0.0, 100.0) |
| S3 全部小时走汇总读 | ✅ |  |
| S3 完成后重复调用不再处理 | ✅ |  |
| S3 整体重跑幂等（仍不重复计数） | ✅ |  |
| S4 首尾不足一小时走原始记录 | ✅ | [('partial', 'raw', True), ('2026-11-15T09', 'summary', False), ('partial', 'raw', True)] |
| S4 已核对小时走汇总、未追平小时走原始记录 | ✅ | [('partial', 'raw', True), ('2026-11-15T09', 'summary', False), ('partial', 'raw', True)] |
| S4 混合路径合计正确 | ✅ | 3 2.0 4.0 |
| S4 整点对整点无首尾碎片 | ✅ | {'2026-11-15T08': 'raw', '2026-11-15T09': 'summary', '2026-11-15T10': 'raw'} |
| S4 按现有负载时间范围查询 | ✅ |  |
| S5 未核对小时读原始记录 | ✅ |  |
| S5 核对一致 | ✅ | {"sensor_id": 905, "hour": "2026-11-16T14", "drift": false, "before": {"cnt": 2, "min_v": 6.0, "max_v": 8.0}, "after": {"cnt": 2, "min_v": 6.0, "max_v": 8.0}, "state": "verified"} |
| S5 核对后切换汇总读 | ✅ |  |
| S5 核对能发现漂移并以原始记录为准修复 | ✅ | {"sensor_id": 905, "hour": "2026-11-16T14", "drift": true, "before": {"cnt": 999, "min_v": 6.0, "max_v": 8.0}, "after": {"cnt": 2, "min_v": 6.0, "max_v": 8.0}, "state": "verified"} |
| S6 空区间返回零计数与空极值 | ✅ |  |
| S6 非有限读数被拒绝 | ✅ |  |
| S6 非法时间被拒绝 | ✅ |  |
| S6 观察员写请求被拒 | ✅ |  |
| S6 缺少时间范围返回422 | ✅ |  |

环境：FastAPI TestClient + SQLite（行锁语义在 MySQL InnoDB 下由 SELECT ... FOR UPDATE 保证，见 backend/migrations/002_readings.md）。
