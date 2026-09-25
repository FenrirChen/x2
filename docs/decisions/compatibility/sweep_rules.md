---
Document-Type: Compatibility Decision
Domain: Rewards
Status: ACTIVE
Updated: 2026-09-25
---
# Decision
扫荡（SecSweep 1027/1028）：要求已通关+充足体力，每次消耗该关 ManualValue，
次数上限 10，只发 MopReward 静态奖，不模拟 DropProp、不读 outsideItems。

# Reason
官方扫荡次数/消耗规则未恢复；MopReward 静态奖是可证实的部分。

# Scope
41 个有 MopReward 的 E_Daily 关。

# Official
PARTIAL（MopReward→RewardData 为官方结构；次数/体力为 Revival 规则）

# User-authorized
YES
