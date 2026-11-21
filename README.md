# 单车桩位调拨台

江湾东线调度员在早高峰前复盘借还尝试，定位缺车、满桩和关站时段，再编辑调拨车行程，对比各站的未成交变化。随项目提供一段 08:00–10:00 的班次、四个站点、两辆调拨车和一份双行程方案。

## 启动

```bash
docker compose up --build
```

打开 [调拨台](http://localhost:18425)。首次启动写入样例班次。SQLite 使用 `cycle_data` 命名卷，之后按已发布版本启动。要新开一份本地演示库，可给 `CYCLE_DB` 指定另一个文件路径。

本地使用 Python 3.12。

```bash
python -m pip install -r requirements.txt
python -m flask --app app.main:create_app run --port 18425
python -m pytest -q
```

## 样例操作

1. 在「借还回放」点选东门地铁 08:15 的槽位查看原始尝试。切到「无调拨基准」可以核对迟报归还 `0011` 排在 08:19 借车 `0012` 前。
2. 在「调拨试算」载入样例方案并试算。未成交从 11 笔减到 8 笔，其中恢复 4 笔，文创园北新增 1 笔未成交。要验证载重，将首趟改成 5 辆。
3. 在「班次留档」查看历史版本、切回选中的班次，或用工具条「重跑班次」复算当前版本。同样的输入和方案沿用原班次编号。
4. 点「下载证据」获取当前查看版本的 JSON。文件带输入摘要、逐行隔离、时间线、试算差量和逐站勾稽。

## 七个业务入口

| 阶段 | API | 站务操作 |
|---|---|---|
| 桩事件收件 | `GET /api/intake`，`POST /api/intake` | 查采信与隔离，上传替换事件 CSV |
| 容量版本 | `GET /api/capacity` | 核对临时围挡、关站及冲突修订 |
| 借还回放 | `GET /api/replay` | 按实际发生时点复原库存 |
| 溢出需求 | `GET /api/demand` | 核对各站未成交尝试和 15 分钟槽位 |
| 调拨试算 | `GET /api/dispatch`，`POST /api/dispatch/preview`，`POST /api/dispatch/publish` | 编辑、试算并发布调拨行程 |
| 库存勾稽 | `GET /api/inventory` | 核对库存、在骑、在途和入账记录 |
| 班次留档 | `GET /api/runs`，`POST /api/runs/rerun`，`POST /api/runs/restore` | 重跑、回切历史、下载证据 |

回放使用匿名在骑车池和离散尝试。调拨试算接受调度员输入的方案，班次、容量和车辆表使用仓内样例配置。路线耗时由输入时点和统一最短用时校验。

[数据字典](docs/DATA-DICTIONARY.md) · [规则与测试索引](docs/DEPTH.md)
