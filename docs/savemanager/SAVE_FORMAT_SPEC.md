# SAVE_FORMAT_SPEC.md — X2 Revival 存档容器格式规范

版本：format_version 1（本文档随格式演进同步更新；importer 必须先检查版本再解析）。
实现：`src/x2server/player/save_manager.py`（单一权威实现，导出与导入共用同一解析器）。

## 1. 容器

- 扩展名：`.x2save`
- 容器：ZIP（deflate），无加密，无 ZIP64。
- 条目（固定顺序、固定时间戳 1980-01-01，保证序列化确定性）：

```
manifest.json          版本/来源/校验和（UTF-8 JSON）
save.json              全部行数据 + 主存档快照（UTF-8 JSON）
blobs/NNNNNN.bin       BLOB 列原始字节（按导出顺序编号，000001 起）
```

- 客户端永远只收到这个容器，不接触 SQL。

## 2. manifest.json

```json
{
  "format": "X2_REVIVAL_SAVE",
  "format_version": 1,
  "server_save_schema": "x2-revival/4",
  "exported_at": 1727750000,
  "source_player": {"player_id": 3, "account": "fenrirchen", "login_count": 25},
  "checksums": {
    "save.json": "<sha256>",
    "blobs/000001.bin": "<sha256>"
  }
}
```

- `source_player` 仅为溯源元数据；**不含**密码、哈希、token、服务器权限。
- `checksums` 必须覆盖 save.json 与全部 blob 条目；importer 逐一校验。
- `source_player.account` 是账号名（非秘密），用于服务器备份命名与展示。

## 3. save.json

```json
{
  "snapshot": { ... players.snapshot 完整 JSON ... },
  "tables": {
    "<表名>": {"rows": [ { "<列名>": <值>, ... }, ... ]},
    ...
  }
}
```

- 新存档表集合必须与审计边界（`save_manager.PLAYER_TABLES`，93 张）**完全一致**：不多、不少。
- 兼容 `x2-revival/3` 的旧 83 表存档。旧文件缺失的八张福利/领奖表保留目标账号已有记录；缺失的两张战斗合成表清空。旧文件中从未保存的数据无法恢复，不能把旧存档视为新版完整备份。
- 导出前校验实际持久化表是否全在边界内；发现新增表未定义归属时返回明确错误，避免静默漏存。
- 序列化：`json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))`，整数不丢精度（Python int / JSON number），UTF-8，禁 NaN/Inf。
- 行按导出时的 rowid 顺序排列。
- 值编码：

| DB 类型 | JSON 编码 |
|---|---|
| INTEGER | JSON number（校验范围 −2^62..2^62） |
| TEXT | JSON string（≤32MB） |
| BLOB | `{"$blob": "blobs/NNNNNN.bin"}` |
| NULL | `null`（仅允许 NULLABLE 列） |

- snapshot 的形状规则与 `PlayerStore.save_snapshot` 一致（nickname/level/heroes 等，`store.validate_snapshot`），导入前强制校验。

## 4. importer 校验流水（全部通过才允许开写）

1. 大小限制：上传 ≤96MB；条目数 ≤128；单条目解压 ≤128MB；总解压 ≤256MB（防 zip bomb）。
2. ZIP 结构：条目名白名单（`manifest.json`、`save.json`、`blobs/…bin` 正则）；重复条目拒绝；加密位拒绝；不允许路径穿越（名字不落盘，只按白名单读）。
3. manifest：字段集精确匹配；format/format_version/server_save_schema 白名单；逐项 sha256。
4. save.json：表集合精确匹配；逐行逐列与活体库 PRAGMA schema 对照——未知列拒绝、缺失 NOT NULL 拒绝、类型错误拒绝、BLOB 必须 `$blob` 编码且引用存在。
5. 引用完整性：battle_receipts/wire.uuid⊆battle_entries.uuid；pending_reward_instances/reward_settlement_audit.run_id⊆economy_runs.uuid；fight_drop_*.report_id⊆observations.id；equipment_*.equip_id 与 snapshot.heroes[].equips[].equip_id ⊆ equipment_instances.id。
6. snapshot 形状校验（store.validate_snapshot）。
7. **任何一步失败：拒绝导入，数据库零接触。**

## 5. 导入执行（单事务）

1. 账号必须离线（HTTP 层检查活动 game TCP session，见 SAVE_MANAGER_IMPLEMENTATION.md）。
2. 服务器自动生成 PRE_IMPORT_BACKUP（见第 7 节）。
3. `BEGIN IMMEDIATE`。
4. 删除目标账号在边界内全部行（join 表按父表 uuid/report_id 集合删除）。
5. 插入导出行：player_id → 目标 id；equipment_instances.id / fight_drop_observations.id 冲突时重映射并同步重写全部引用（含 snapshot JSON）；player_mail.id 一律重新分配；全局键（uuid 族/request_key）与他号冲突时整族一致重映射。
6. 更新 players.snapshot；提升 sqlite_sequence；`PRAGMA foreign_key_check`。
7. `COMMIT`；任何异常 `ROLLBACK`，导入前状态原样保留。

## 6. 一致性与确定性

- 导出在单只读事务（`BEGIN DEFERRED`）内完成，快照内部一致。
- manifest/checksums/行序/键序全部确定；仅 `exported_at` 反映导出时刻。
- 同一账号重复导出 save.json 逐字节一致。

## 7. 服务器内部备份（PRE_IMPORT_BACKUP）

- 位置：`<DB 目录>/server_backups/save_import/player_<player_id>/latest.x2save`（只保留最近一份；完整写入并 fsync 后原子替换；历史备份启动时核对归属后清理）。
- 内容：导入动作前一刻的完整 export_save 容器——可用同一 importer 人工恢复（管理操作）。
- 审计：`server_backups/save_import/import_audit.log`（JSON 行：账号/备份路径/逐表行数/来源 player），不记录任何凭据。

## 8. 版本迁移框架

- importer 只接受 `ACCEPTED_SCHEMAS` 中的 `server_save_schema`；遇到未知 schema 报"需要迁移"并拒绝。
- 未来 schema 变更流程：新增 schema 字符串 → 在 parse 前插入 `MIGRATIONS[(old_schema, new_schema)]` 迁移函数（v1 暂为空表，但解析点已固定在 `_validate_manifest`，迁移钩子只需在那里接入）→ 老存档经迁移后进入新 importer。禁止直接报废旧档。

## 9. 排除项

见 SAVE_DATA_AUDIT.md 第 5 节 EXCLUDED_FROM_SAVE（账号身份/活动字段/运维表/内存态/审计/序列）。存档内不存在任何认证凭据。
