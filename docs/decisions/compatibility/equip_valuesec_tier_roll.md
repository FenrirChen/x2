---
Document-Type: Compatibility Decision
Domain: Equipment
Status: ACTIVE
Updated: 2026-09-25
---
# Decision
EquibAttrib.ValueSec 三档取值采用**逐段升级链**随机（Revival 兼容解释）：

- 从 `ValueSec[0]` 起步；
- 以 `ChanceSec[0]` 概率升级到 `ValueSec[1]`；
- 若已升级，再以 `ChanceSec[1]` 概率升级到 `ValueSec[2]`。

等价分布：
- `ChanceSec=[60,40]`（主属性 src0/src1 全部 192 行）→ 三档概率 **40% / 36% / 24%**；
- `ChanceSec=[80,20]`（副词条 src2/src3 全部 192 行）→ 三档概率 **20% / 64% / 16%**。

适用范围：
- 主属性初始值：`EquibAttrib[star, src0, type]`；
- 副词条初始值：`EquibAttrib[star, src2, type]`；
- 强化增量：`EquibAttrib[star, src3, type]`（逐次强化事件各掷一次链）。

# Reason
客户端对 ChanceSec 零消费（EquibAttrib 行仅 CollegeModule 两个显示函数获取、均只读
ValueSec 顶档；GetAllItem 0 调用者），官方"3 档 ↔ 2 权重"映射不可恢复。
逐段升级链是唯一与字段命名（Sec=段）和常数结构自洽的候选模型；须选定一种才能实现
FIX-E2 的数值生成。

# Scope
仅 Revival 服务器装备实例工厂的数值取档与强化增量 roll（equipment_server_fix_plan.md
FIX-E2 / FIX-E4）；不改变 Star=quality、条数档 65/35 决策、DroopLimit3 带收敛等既有结论。

# Official
NO（官方取档算法客户端不可见；本规则是对官方数据结构的兼容解释）

# User-authorized
YES（USER_DECISION，2026-09-25）

# Notes
- 不得在任何文档/代码注释中把逐段升级链表述为官方已恢复算法；
- 官方事实保持不变：ValueSec 三档与 ChanceSec 均来自客户端官方表（equibattrib_full.json
  384 行）；ChanceSec 客户端零消费，映射关系官方未知；
- 现行 `EquipmentService.strengthen` 的 min-max 均匀 roll 在实施本决策时应替换为逐段链
  （src3，每事件一掷）——属实施项，当前不实施；
- 若未来获得官方取档证据（实机样本/服务器数据），以新 USER_DECISION 替换。
