---
Document-Type: Compatibility Decision
Domain: Equipment
Status: ACTIVE
Updated: 2026-09-25
---
# Decision
EquibAttribBD 初始词条档位选择（Revival 兼容策略）：
- 4★/5★/6★（存在 base=Min 档与 Max 档两档的星级）：选 base/Min 档行概率 **65%**，Max 档行 **35%**；
- 1★/2★/3★：仅存在唯一档（base 行），固定不变，不做 65/35；
- 实际初始副词条数 = 所选 EquibAttribBD 行的 `MinorAttrNum`（官方事实，本决策不改变），
  条数合法性仍受 `EquibStage[Star].MinorListMin..MinorListMax` 约束。

# Reason
官方服务器掉落/发放路径的 AttribBD 选行规则客户端不可见（EquibAttribBDManager.GetItem
仅 GM UI 两处调用，MinorAttrNum 为服务器输入；GM opt=15 证明行=构建规格）。
条数是行常量、非独立 roll；需要一个确定的选行策略才能实现 FIX-E2。

# Scope
仅 Revival 服务器装备实例工厂（equipment_server_fix_plan.md FIX-E2）的选行环节；
不改变 Star=quality、DroopLimit3 带收敛、EquibValue 预算等任何官方语义。

# Official
NO（官方 65/35 或其他选行概率不可考——客户端无证据）

# User-authorized
YES（USER_DECISION，2026-09-25）

# Notes
- 不得在任何文档/代码注释中把 65/35 表述为官方概率；
- 若未来获得实机官方初始条数分布样本，可用样本拟合替换此策略（需新的 USER_DECISION）。
