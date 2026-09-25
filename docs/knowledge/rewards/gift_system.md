---
Document-Type: Current Knowledge
Domain: Rewards
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - docs/history/2026-09-25_04_gift_runtime_semantics.md
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# Gift 系统

`Example.Gift{GiftGroup, AwardType, Probability[], GiftValue[], Num[], GiftShow[], ItemNum, EquibNum}`；
`GiftEAwardType={None=0, material=1, Random=2, RandomInterval=3, Pick=4, BlindBox=5}`。

| AwardType | 已确认语义 | 证据级 |
|---|---|---|
| E_material | 固定：GiftValue 直出（客户端解析器与服务器发放一致） | A |
| E_Random | **单次加权抽取**：GetProbability(rng, Probability) 选一个 GiftValue；**无 Σ=100 约束** | A（原生函数）/B（调用方孤立） |
| E_RandomInterval / E_Pick / E_BlindBox | 未恢复（Num 维度/交互语义未知） | UNKNOWN |

- **发放=SERVER_EXECUTED**：结算/扫荡/邮件全部以解析后的 RewardData 到达客户端；
  客户端 33 处 GiftManager 调用全为 UI 预览，checkout 路径零调用。
- 服务器按表发奖=重建官方服务器行为（REVIVAL_COMPATIBILITY 层面成立），当前实现应去掉
  ΣProbability=100 约束（见 [server_fix_plan.md(server_fix_plan.md) FIX-1）。
- 消费者图谱与解析器反汇编：[gift_runtime_semantics.md(gift_runtime_semantics.md)。
