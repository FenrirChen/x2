# DropValueID vs stamina 分析摘要（2026-09-26）

数据：analysis/drop_budget/section_stamina_dropvalue.csv（3203 关全量）。

## 关键计数
- 有 DropValueID 的关卡：3043；无：160（迷宫/测试类）
- 唯一 DropValueID：341；被 >1 关卡共享：85
- 共享且跨体力（同一配置不同 ManualValue）：8 组（全部为 E_Activity/E_TowerDefense 等活动族，
  例：10660211 被 108 个关卡共享，体力跨 12/18/24/30/36）
- 公式：DropValueID = 10600000 + SectionID%100000（310/341 命中；其余为有意共享/手工错位）

## 资源本族（1 关 1 配置）
- 金币本 2130101-109：体力 6/12/18/24/30/6/12/18/24，各自独立 DropValueID（10630101-109）
- 经验本 2130201-205：体力 12/18/24/30/36，独立 DropValueID
- 兽主本 2133101-110 / 2133201-209 / 2133301-309：全部体力 30，30 个各不相同 DropValueID

## 判定
- STAMINA_DIRECTLY_DETERMINES_BUDGET = REJECTED
  （同体力 30 的兽主本 30 关各配独立键；8 组共享键跨体力使用——若预算=f(体力)，
  一档一配置即可，无需按关卡族×月相拆分）
- STAMINA_CORRELATED_WITH_BUDGET_CONFIG = MODERATE
  （同族内难度↑→体力↑→新配置键，共变明显；但键≠值，且跨体力共享配置的反例存在）
- 最可能官方关系（B 级推断）：预算 = 每关卡按"设计掉落量"独立配置的服务器配额，
  键 = DropValueID；体力是经济门槛，与难度共变而非预算自变量
- 官方每组预算数值：SERVER_DATA_LOST
