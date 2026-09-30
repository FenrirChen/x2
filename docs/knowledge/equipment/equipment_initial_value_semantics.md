---
Document-Type: Current Knowledge
Domain: Equipment
Status: AUTHORITATIVE
Updated: 2026-09-25
Evidence-IDs: CLIENT_IL2CPP_2_4, CLIENT_FULL_TABLES_2_4, CLIENT_DUMP_CS
---

# 兽主初始数值语义（主/副词条数值来源：EquibAttrib 阶梯 + EquibAttribBD 固定盘）

机器可读：`analysis/equipment/equipment_initial_value_semantics.json`、`equibattrib_full.json`
（384 行含 AttribSRC 的完整重解析）。相关：[equipment_initial_affix_semantics.md](equipment_initial_affix_semantics.md)（条数）、
[equipment_star_quality_semantics.md](equipment_star_quality_semantics.md)（星级）。

## 1. 四张表的分工（全部 A 级）

| 表 | 职责 | 关键字段 |
|---|---|---|
| **EquibBase** | **只抽"什么属性"**（类型池+权重），无数值 | MainAttrType[]（每部件单候选，Chance 恒 [100]）、MinorAttrType[]（16 类型池子集）+ Chance[] 加权 |
| **EquibAttrib** | **官方数值宇宙**：per (星, src, 类型) 3 档离散阶梯 + 2 权重 | ValueSec[3]、ChanceSec[2] |
| **EquibAttribBD** | **授权固定盘**（exact 值），用于固定发放/GM | MainAttr[type,value(,g1,g2)]、MinorAttrType/Value[5]、StreNum/StreValue[5] |
| **AttribType** | 属性元数据（名称/百分比/显示上下限 ±100000） | **不是 roll 范围** |

## 2. EquibAttrib：数值宇宙（384 行 = 6星 × 4 src × 16 类型）

`EquibAttribManager.GetItem(star, src, type)`（0x1CAF32C）。src 语义（A，来自
CollegeModule 两个 consumer 的调用对）：

| src | 含义 | 证据 |
|---|---|---|
| 0 | **主属性基础值**阶梯 | GetEquipBaseProperty isMain→src0；GetEquipMaxProperty 主公式基项 |
| 1 | **主属性成长值**阶梯 | GetEquipMaxProperty 主：`max = src0top + src1top × level` |
| 2 | **副词条基础值**阶梯 | GetEquipBaseProperty minor→src2 |
| 3 | **副词条强化增量**阶梯 | GetEquipMaxProperty 副公式用 src3；Revival strengthen catalog 即取 src3 |

- ValueSec = 3 档升序离散值（例：4★ 主HP src0=[54,64,68]、4★ 副HP src2=[21,25,26]、
  4★ 副HP 增量 src3=[10,12,13]）；ChanceSec = 2 权重（src0/1 恒 [60,40]，src2/3 恒 [80,20]）。
- **ChanceSec 客户端零读取（A 级反证）**：EquibAttrib 行的全部获取途径 = GetItem 两个调用点
  （均只读 ValueSec 顶档）+ GetAllItem（0 调用者）。因此"3 档如何与 2 权重对应"官方规则在服务器。
  候选模型（仅记录，不可证实）：①逐段升级链（Sec=段：tier0 起步，ChanceSec[0]% 升 tier1，
  再 ChanceSec[1]% 升 tier2 → 主 [60,40] 分布 40/36/24，副 [80,20] 分布 20/64/16）；
  ②tier1/tier2 互斥加权、tier0 保底（60/40 归一化后 tier0 概率为 0，需隐含参数，存疑）；
  ③3 档为平行变体（如难度/内容档）而非 roll 空间，ChanceSec 非概率。
  恒定性（384 行权重不变）提示它是公式级常数而非逐条调参；顶档=规范值有旁证
  （两个显示函数取顶档；4★ AttribBD 盘副词条=src1 顶档精确命中）。
  **Revival 已选定模型①（逐段升级链）为兼容策略——REVIVAL_COMPATIBILITY/USER_DECISION
  2026-09-25，见 decisions/compatibility/equip_valuesec_tier_roll.md；非官方算法。**
- **官方数值形态 = 多档离散 + 权重，不是连续 min-max 随机**（表结构事实 A；具体取档算法在服务器）。
- 消费者仅 `GetEquipBaseProperty`(0x1B0156C，返回 ValueSec 顶档)/`GetEquipMaxProperty`
  (0x1B010F8)（图鉴显示）。**客户端无任何生成期数值消费**：CollegePurify 54 个方法 0 Random、
  0 EquibAttrib（全 Send*Opt 服务器驱动）。

## 3. EquibAttribBD：固定盘，不是随机数值源（本轮关键修正）

- **base 行（QQ000000/QQ000001/QQ000100）全部数值=0**——它们只是条数模板（MinorAttrNum），
  **不可能是数值来源**。因此"随机掉落件的数值"不可能来自所选条数档行。
- **filled 行（QQ000101-106）**= 6 部位精确盘：主属性(类型,值) + 副词条槽位(类型,值)，
  强化增量全 0。**1★/2★ 盘值超出全部阶梯**（如 1★主104=200 vs src0=[102,121,128]）→
  盘是独立授权数据。4★ 盘副词条恰为 src1 顶档、5★/6★ 盘副词条落在 src2 区间内、
  seasonal 主属性=src0[0]——说明盘与阶梯同源但盘可自由授权。
- **seasonal 行（161511xx）**：唯一带 MinorAttrStreNum/StreValue（逐槽强化增量）的行；
  `EquibLevel` 全 66 行=0（字段存在未用）。
- GM `C2L_Cheat{opt=15, values=[equipId, attrbdId]}`：盘值即最终 Param 的直接依据。

## 4. 生成模型（对应任务问题）

```
主属性类型: EquibBase[TypeId].MainAttrType/Chance（固定单候选）
主属性数值: 随机件 → EquibAttrib[star, src0, type] 3 档阶梯（取档在服务器）
            固定件 → AttribBD 盘 MainAttr[1]
副词条类型: 随机件 → EquibBase.MinorAttrType/Chance 加权；固定件 → 盘槽位
副词条数值: 随机件 → EquibAttrib[star, src2, type] 3 档阶梯
强化增量:   src3 阶梯（随机件）/ 盘 StreNum/StreValue（seasonal 盘）
```

- **base/max 条数档不决定数值档**（base 行无数值）；数值与条数是两条独立决策线。
- **强化与初始分离**（表层面 src2/src3 分离、盘内 MinorV/StreV 分离；机制层面强化走
  EquipStrengthen 服务器写回）。

## 5. Level=0 官方基础数值恢复度：PARTIAL（结构完整、取档规则未知）

- **完整恢复**：EquibAttrib 全 384 行阶梯（equibattrib_full.json）+ 66 行盘 →
  任意 (星, 类型) 的 3 档官方值与全部固定盘值。
- **未恢复**：随机件在 3 档中的取档算法（ChanceSec 的确切用法）——服务器侧。
- Revival 现状审计（未发现自创值冒充官方）：seed catalog=官方盘直复制（政策自证
  TEST_COMPAT）；strengthen catalog=官方 src3 阶梯，但 roll 用 min-max 均匀
  （**官方应为 3 档离散+ChanceSec，均匀 roll 属 REVIVAL_COMPAT**）。

## 6. Revival 兼容数值规则（全部已决策，实施见 server fix plan）

1. **随机件数值取档：逐段升级链（已决策）**——ValueSec[0] 起步，ChanceSec[0]% 升 tier1，
   再 ChanceSec[1]% 升 tier2；主 src0=[60,40]→40/36/24，副 src2 与强化 src3=[80,20]→20/64/16。
   **REVIVAL_COMPATIBILITY/USER_DECISION（2026-09-25，
   decisions/compatibility/equip_valuesec_tier_roll.md），非官方算法。**
2. 掉落件条数档选择：65/35（USER_DECISION 2026-09-25）。
3. 主属性成长（2026-09-30 修复）：每次成功升级在 Av1 上增加
   `EquibAttrib[star, src1, type]` 的每级成长值；每件首次强化按已有逐段链
   兼容规则取档并保存到 `equipment_main_growth`，后续等级与重启沿用同一值。
   新掉落 Lv0 兽主满足 `Av1 = 初始值 + 成长值 × Level`。
   按用户本轮缩小后的范围，不补算历史缺失成长、不改写已强化兽主；
   旧兽主从下一次成功升级开始增加主属性。副属性的事件、选择、增量算法均保持现状。
4. 强化增量 roll：按 src3 阶梯逐段升级链（每事件一掷）——实施时替换现行 min-max 均匀 roll
   （后者同为兼容实现，见 equipment_strengthen_catalog.json interpretation）。
