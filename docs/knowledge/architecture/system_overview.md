---
Document-Type: Current Knowledge
Domain: Architecture
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - docs/history/2026-09-22_04_first_contact_plan.md
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 系统总览

Revival 项目 = 官方《解神者》2.4 客户端 + 本地兼容服务器（`src/x2server/`）。

```
官方客户端(Revival v0.2, 仅改 Login_Url/packageType)
  ├─ HTTP Bootstrap: 登录身份/地址下发        (src/x2server/bootstrap/)
  ├─ TCP 长连接: protobuf 子集协议, 消息注册   (src/x2server/network/, protocol/, messages/)
  └─ 业务域: 登录/大厅/物品/英雄/装备/魂器/技能/战斗/结算/任务/商店/抽卡/聊天
                                        (src/x2server/player/)
持久化: 单 SQLite (players.snapshot 主体 + 24 张业务表)   (src/x2server/player/store.py 等)
静态数据: 服务器内置目录 + analysis/ 静态表目录           (src/x2server/data/)
```

权威领域文档索引见 [../../PROJECT_INDEX.md(../../../PROJECT_INDEX.md)（仓库根）。
服务器结构细节: [server_architecture.md(server_architecture.md)。
