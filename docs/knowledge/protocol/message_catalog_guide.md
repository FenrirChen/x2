---
Document-Type: Current Knowledge
Domain: Protocol
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none)
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 消息目录使用指南

1. 全量目录：`analysis/protocol/protocol_catalog.json`（Evidence: PROTOCOL_CATALOG）
   —— 每条含 message_id / protobuf_fields / send_channels / paired_response /
   client_status / server_registered / business_domain。
2. 重新生成：`python tools/analysis/build_protocol_catalog.py`。
3. 服务器侧注册：`src/x2server/protocol/registry.py` + `src/x2server/messages/*`；
   dispatcher 只调用显式注册的 handler，未实现消息回空。
4. 未实现但客户端会发的高价值清单：`analysis/protocol/unhandled_high_value.json`
   （按业务域分组并附静态数据可得性注记）。
5. 纪律：`NO_SEND_POINT_IN_2_4` 的消息不写 handler；enum 存在 ≠ 客户端会发。
