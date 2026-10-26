---
Document-Type: Compatibility Decision
Domain: Client / Shop
Status: ACTIVE
Updated: 2026-10-27
---
# Decision
把数量弹窗的「最多」按钮改成 max/min 切换，**必须改客户端**：

- 新增 [patch_quantity_max_toggle.py](../../../tools/savemanager/client/patch_quantity_max_toggle.py)：
  按字节特征定位 `InputItemNum_ToMax` 入口，把它改成一条 `b <cave>`，真实逻辑放进
  自动定位的 code cave。

原实现只有「一键到上限」：

```asm
InputItemNum_ToMax:
    stp x20, x19, [sp, #-0x20]!
    stp x29, x30, [sp, #0x10]
    add x29, sp, #0x10
    mov x19, x0
    ldr w8,  [x19, #0x20]   ; mMaxNum
    mov w9,  #999
    cmp w8,  #999
    csel w20, w9, w8, gt    ; w20 = min(mMaxNum, 999)
    cbnz x19, +2
    bl   <null guard>
    str w20, [x19, #0x20]   ; mMaxNum = w20
    ...
    b    InputItemNum_SetNum
```

补丁后：

```asm
    ; 原序言 4 条指令（可重定位，原样搬进 cave）
    ldr w8, [x19, #0x10]    ; _ItemNum
    ldr w9, [x19, #0x20]    ; mMaxNum
    cmp w8, w9
    b.ge to_min             ; 当前值已经到上限 -> 回到 mMinNum
    <原 clamp-999 + guard + SetNum>   ; 否则保持原行为：一键到上限
to_min:
    ldr w1, [x19, #0x24]    ; mMinNum
    ...
    b InputItemNum_SetNum
```

# Reason
`ShopCheckWnd_OnInit` 只给 `InputItemNum` 接了三个按钮：`-`、`+`、`最多`
（`InputItemNum_SetMin(1)` 只写内存里的 `mMinNum`，没有对应的「最小」按钮）。
所以一旦误按「最多」，值停在 `min(mMaxNum, 999)`，关掉弹窗再打开也不会重置——
只有手动点几百次 `-` 或者杀进程。**服务端不参与这个上限**：`InputItemNum` 的
`mMaxNum` 来自客户端预制体，服务端只校验购买数量是否超过剩余库存/货币。
因此本 PR 是纯客户端改动，服务端不需要任何配套修改。

# Scope
- 只改 `lib/arm64-v8a/libil2cpp.so`：`InputItemNum_ToMax` 入口 4 字节 + 一段
  100 字节的 cave，其它字节不变（脚本会逐个字节校验）。
- 结构体偏移（与 `InputItemNum_SetNum` 一致）：`_ItemNum 0x10`、
  `mDefaultNum 0x1c`、`mMaxNum 0x20`、`mMinNum 0x24`。
- 2.4 APK 内的 so：88855552 字节，`sha256 3b45b697…`，命中
  `0x16E8468`，cave `0x429BC70`，null guard `0x3F564F0`，
  `SetNum 0x16E7A90`。
- `work/apk` 下那份 so 是另一构建：88872784 字节，`.text` 偏移 `-0x7B0`，
  同一特征命中 `0x16E8C18`，guard `0x3F5A21C`，`SetNum 0x16E8240`。
  脚本不写死任何 RVA：hook 按 8 word 特征找（要求唯一命中），guard / `SetNum`
  从 hook 自身的 `bl` / `b` 解码，cave 用 `patch_title_voice.find_cave` 找。

# Official
NO（官方只有「最多」，没有回到最小的入口）

# User-authorized
YES（USER_DECISION，2026-10-27）

# Usage
```powershell
# 1. 从 APK 取出 lib/arm64-v8a/libil2cpp.so
# 2. 打补丁（脚本自己校验特征唯一、guard/SetNum 解码、cave 反汇编）
python tools\savemanager\client\patch_quantity_max_toggle.py <libil2cpp.so> <patched.so>
# 3. 把 patched.so 按原条目名（lib/arm64-v8a/libil2cpp.so）替换回 APK
# 4. 用本地开发密钥重新签名后才能安装（签名步骤不在本工具内）
```

脚本只接受唯一命中：特征命中 0 处或多处都会直接报错、不产出文件。

# Cave allocation
`find_cave` 会跳过已占用的 trampoline：

- `0x42B02C0` — 存档管理登录按钮（`patch_il2cpp.py`）
- `0x429B870` — 大厅英雄「标题」语音（`patch_title_voice.py` 自动定位到的第一段
  1024 字节零区）

所以本补丁落在同一段已审计零区的尾部 `0x429BC70`（512 字节），不会把标题语音的
cave 顶走，`analysis/client_release_20261024` 里记录的地址仍然有效。补丁先打或后打
都可以：两个工具都只写自己找到的零区，且都校验过写入范围。

# Notes
- 值仍受 `min(mMaxNum, 999)` 限制：库存/上限小于 999 时「最多」依旧到那个上限。
- 再次按「最多」回到 `mMinNum`（`SetMin(1)`，即 1），不会再需要手动点几百次 `-`。
- 只动 `InputItemNum_ToMax`：`SetNum` / `SetMin` / `ToMin` 都保持原样，其它弹窗
  （商店单买、礼包批量、角色升级材料等）共用同一套逻辑，行为一致。
