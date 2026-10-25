---
Document-Type: Compatibility Decision
Domain: Client / Favor
Status: ACTIVE
Updated: 2026-10-25
---
# Decision
放开「默契度满级后继续送礼」的客户端闸门，**必须改客户端**：

- 新增 [patch_favor_gift_gate.py](../../../tools/savemanager/client/patch_favor_gift_gate.py)：
  按字节特征定位 `FavorSendGift_CheckAttchLevelMax` 的满级判定并等长改写。

```
cmp  w0, w21          ; w0 = Favor.FavorLevel, w21 = FavorabilityHero.LevelLimit
cset w23, lt          ; w23 = (FavorLevel < LevelLimit)     -> 原字节 f7 a7 9f 1a
```

改成：

```
cmp  w0, w21
mov  w23, #1                                               -> 新字节 37 00 80 52
```

`w23` 之后与 `Favor.GiftsTimes < SendGiftControl.ReceiveNumber`(99999) 相与，写
`Selectable.set_interactable` / `UIImageGray.set_gray`。改写后满级也保持可点。

# Reason
客户端的满级判定只读 `FavorabilityHero.LevelLimit`（39 个英雄全部为 10，
`FavorabilityLevel` 虽然定义到 20 级但客户端没有其它提升入口），而服务端
`_advance()` 本来就在满级后继续累加 `exp`、等级封顶 `LevelLimit`——也就是说服务端
早就允许满级继续送礼，唯一的阻塞是客户端把按钮置灰。**因此本 PR 是客户端改动，
服务端无需再改；等级仍封顶 10，只继续累计默契度数值，不会出现 20 级。**

# Scope
只动 `lib/arm64-v8a/libil2cpp.so` 中的 4 个字节，不新增/删除存档字段：

- 补丁前：`1f 00 15 6b f7 a7 9f 1a`（`cmp w0,w21` / `cset w23,lt`）
- 补丁后：`1f 00 15 6b 37 00 80 52`（`cmp w0,w21` / `mov w23,#1`）
- 2.4 APK 内的 so：88855552 字节，`sha256 37f092f1…`，命中地址 `0x18B7EF0`
  （补丁字 `0x18B7EF4`）。
- `work/apk` 下的 so 是另一构建：88872784 字节，`.text` 起点相差 `-0x7B0`，
  同一特征命中 `0x18B86A0`。脚本只按特征定位、要求唯一命中，不写死 RVA，两版都能
  正确落点。

# Official
NO（客户端原本就是「满级不可送」，放开是 Revival 的兼容策略）

# User-authorized
YES（USER_DECISION，2026-10-25）

# Usage
```powershell
# 1. 从 APK 取出 lib/arm64-v8a/libil2cpp.so
# 2. 打补丁（脚本自动校验特征唯一与反汇编结果）
python tools\savemanager\client\patch_favor_gift_gate.py <libil2cpp.so> <patched.so>
# 3. 把 patched.so 按原条目名替换回 APK
# 4. 用本地开发密钥重新签名后才能安装（签名步骤不在本工具内）
```

脚本会对输入打印体积与 SHA-256；特征命中数不是 1、或改写后 capstone 解不出
`cmp w0,w21` / `mov w23,#1` 时直接报错，不产出文件。

# Notes
- 满级后仍可继续送礼，但默契度等级不会超过 10（`LevelLimit`），只继续累计数值。
- 语音侧的「满级补解锁 1350111」已在服务端完成（见
  [favor_gift_voice_at_level_limit_20261025.md](favor_gift_voice_at_level_limit_20261025.md)），
  即使不打本客户端补丁，语音也不会再丢；本补丁恢复的是送礼入口本身。
- 不要在 `FavorMap` 里谎报 9 级来绕过按钮：`GetFavorLevel` 同时被纸鹤页、头像、通讯
  等等级判定读取，会连带改错显示。
