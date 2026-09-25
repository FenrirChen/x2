---
Document-Type: Current Knowledge
Domain: Economy
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - docs/history/2026-09-23_01_client_economy_data_audit.md
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 经济系统

**货币（A，CurrencyType 表 46 行）**：901=E_Gold→Item 1237901(金币)；902=E_Money→1237902(光辉)；
903=E_Silver→1237903（**迷宫/场内银币，非账号金币**）；900→1237900(因果)。战斗内
FightItemBag.AddGold 只写场内桶，账号入账靠服务器按 CurrencyType.ItemID 落账。

**固定奖励**：FirVReward(619 关)/VReward(2439 关)/MopReward(41 关 E_Daily)→Gift→Item
静态闭环（Evidence: SECTION_REWARD_CATALOG）。E_Random 按 FIX-1 归一化权重执行。

**商店**：25 店/1,567 商品行有价格/货币/周期；**GoodsID→ItemID/Num 客户端无映射**
（仅 17 条 Item.QuickBuyID 反查）——商品内容由服务器 L2C_Goods 决定（第三方独立资料同结论）。
商店当前固定拒绝（防成功空列表崩溃客户端）。

**体力**：每小节按 ManualValue 扣费（用户指定规则），失败退款；自然恢复/购买未实现。

**日周任务/活跃**：40 任务静态全解；事件源部分接入；活跃宝箱 310 已有发送点但 boxId
索引语义需实测样本。细节：[missing_evidence_followup.md(missing_evidence_followup.md)、
[client_economy_data_audit.md(client_economy_data_audit.md)、根 NEED.md。
