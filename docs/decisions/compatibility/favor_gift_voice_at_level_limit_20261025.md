---
Document-Type: Compatibility Decision
Domain: Favor
Status: ACTIVE
Updated: 2026-10-25
---
# Decision
把「收到喜欢的礼物」语音（条件 1350111）在**默契度满级**时补解锁：

- [appearance.py](../../../src/x2server/player/appearance.py) 新增
  `dubbing_level_limits()`（读 `favor_catalog.json` 的 `FavorabilityHero.LevelLimit`）。
- `dubbing_unlocked()` 的 `gift` 分支在 `favor_liked_gift` 之外，再接受
  `FavorLevel >= LevelLimit`；等级只看当前存档，不写 `appearance_voice_unlock`。

# Reason
客户端按钮闸门 `FavorSendGift_CheckAttchLevelMax` 把
`FavorModule_GetFavorLevel_1`（服务端 `FavorMap` 的 `FavorLevel`）与
`FavorModule_GetMaxLevelLimit`（只读 `FavorabilityHero.LevelLimit`，39 个英雄全部为
10）比较：

```
cmp  w0, w21      ; w0 = FavorLevel, w21 = LevelLimit
cset w23, lt      ; w23 = (FavorLevel < LevelLimit)
```

`w23` 与 `Favor.GiftsTimes < SendGiftControl.ReceiveNumber`(99999) 相与后写入
`Selectable.set_interactable` / `UIImageGray.set_gray`。满级后送礼按钮被置灰，而官方
只在礼物气泡播放时才发 `C2L_SaveHeroDubbing`(688)，1350111 因此永远拿不到。服务端
`_advance()` 本来就在满级后继续累加 exp、等级封顶，所以补解锁只影响显示，不伪造
`FavorMap` 等级。

# Scope
服务端 1 个文件 + 1 条回归用例：

- 满级前保持锁定（送过偏好的礼物仍按 `favor_liked_gift` 解锁，1 级即生效）。
- 满级后 `C2L_QueryHeroDubbing` 直接带出该语音，`C2L_SaveHeroDubbing` 也回 `code 10`。
- 不新增存档字段，不重复推送；等级回落时自动恢复锁定。

# Official
NO（补解锁是 Revival 对客户端硬门槛的兼容策略，官方无此回退）

# User-authorized
YES（USER_DECISION，2026-10-25）

# Notes
- 客户端侧放开满级送礼按钮是独立改动（`libil2cpp.so` 的 `cset w23,lt` → `mov w23,#1`），
  不在本 PR 内；本 PR 只保证语音在未打客户端补丁时也能解锁。
- 复检结论：官方链路只在 `ExpressionAnimStatus.Status=5` 的某个气泡真正播放时才发
  688，每个英雄的偏好礼物有 1~4 件而只挂 1 条 1350111，所以原版送偏好礼物也**不保证**
  解锁，与等级无关；本服对任意 `SendGiftControl.FavoriteGoodID` 成交即解锁。
