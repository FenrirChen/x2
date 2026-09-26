---
Document-Type: Compatibility Decision
Domain: Rewards
Status: SUPERSEDED（2026-09-26：E_ReportCurrency 折算机制实装后，金币本手打收入 = 代理物折算金（见 equip_report_currency_conversion.md）；MopReward 金量回归扫荡专用）
Updated: 2026-09-25
---
# Decision
金币资源本（2130101–2130105）手打胜利结算的金币数量 = 各关 MopReward 中扣除普通
VReward 后的独立金币组数量（2078/4678/9356/14552/20788）。

# Reason
官方动态金币公式依赖 IsADC 候选与服务器数据（失传）；影响面仅 5 关；用户明确授权。

# Scope
仅 2130101–2130105；不复制到其他资源本；不执行整个扫荡奖励。

# Official
NO（官方按罐子/金币怪动态计算，公式未恢复）

# User-authorized
YES（2026-09-24）

# Notes
若 outsideItems 已含 1237901，由兼容金币量替代避免重复；1237903 永不入账号。
