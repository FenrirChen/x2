# 登录进主界面复播看板娘「标题」语音

## 现象与数据证据

Dubbing 表里 39 行「标题」语音，每行一个英雄：`DubbingName=1350035`、`Locked=1`、
`UnlockConditions=1350123`、`SoundID = heroId * 100 + 8`（39 行全部成立）。音频资源在包内，
例如 TianShu(1014) → SoundID 101408 → `event:/Sounds/Vocal/JP/Hero/TianShu/Vo_H1014_TianShu_Logo`，
`Bank=Vo_JP_H1014_Logo.bank`（另有 `BankKR` 一套韩语）。

客户端**没有任何代码播放它**：`GameAPI.PlayVoice` 只有 10 个调用点（战斗胜利／获得新英雄／
剧情气泡／语音档案点击／看板气泡…），没有「进主界面」这一项，所以它在语音档案里一直挂着锁。
播放链本身是好的：`PlayVoice(DubbingId)` 内部 `DubbingManager.GetItem` 拿到行，用行里的
`SoundID`／`Vocal` 交给 FMOD；`FMODManager.PlaySound` 自己会 `LoadBank`（按语音语言选 JP/KR），
所以不需要额外加载 bank。

## 触发点

`MainHallFSM.MainAniEnter` 就是「点开始跃迁、登录完成进主界面」那一拍（实测日志确认）：原函数
切 BGM、禁点 2 秒、播看板娘入场动画。在这一拍补一次标题语音，与入场动画同起同落。看板娘 =
`AccountInfoModule.get_CurHero()`（登录页与主界面读的是同一个，换看板语音就跟着换）。

与登录按钮跳板的关键差别：**这里必须是附加式**。先执行原函数、再补语音、最后跳回 `entry+4`；
不能像 `patch_il2cpp.py` 那样替换目标，否则入场动画／BGM／禁点都不会执行。

## 修改

| 文件 | 内容 |
|---|---|
| `patch_title_voice.py` | 首指令 hook + code cave：`dlopen("libx2save.so")` → `dlsym("x2_play_login_title_voice")` → 以 (this, handle) 调用 → 恢复 x0..x15 → 还原被搬移指令 → `b` 回 `entry+4`。cave 自动避让已占用的存档管理 cave；`dlopen`/`dlsym` 的 PLT 桩从 `.plt` 自动解析；内建 capstone 校验：被搬移指令必须位置无关、末尾必须跳回 `entry+4` 且不得 `ret`、hook 与 cave 之外不得有字节变化 |
| `x2save_bridge.c` | 新增导出 `x2_play_login_title_voice(main_hall_fsm, il2cpp)`：全部按名字解析，进程内只播一次 |
| `test_bridge.c` | 新增契约用例（见下） |

用法（`--rva` 处填本包 dump.cs 里 `MainHallFSM.MainAniEnter` 的 RVA）：

```sh
python tools/savemanager/client/patch_title_voice.py \
    lib/arm64-v8a/libil2cpp.so out/libil2cpp.so --rva 0x13be1d4
```

- 字段与调用约定（实测踩过的坑）：
  - 这三个方法在 metadata 里都是实例方法，但函数体从不读 `this`；客户端自己调用时 `x0=0`、
    `x2=0`，所以这里也直接调 `methodPointer`。**不要换成 `il2cpp_runtime_invoke`**：它把 int32
    返回值装箱成对象，`get_CurHero` 读到的会是 `Il2CppObject` 头（实测拿到 hero=-537777136 这种垃圾值）。
  - `DubbingManager.GetAllItem()` 返回的是 `DubbingArray` 包装类：`Keys`(List&lt;long&gt;)@0x10、
    `Items`(List&lt;Dubbing&gt;)@0x18。0x10 那格是 Keys，直接当 `List<Dubbing>` 读会遍历到一堆 int64
    ——实测因此查不到行。桥里按字段名取 `Items`，再按 `_items`／`_size` 遍历。
  - 行以 `(HeroId, DubbingName==1350035)` 命中后取 `DubbingId`；不依赖任何 `DubbingId` 公式
    （`hero*1000+308` 已证伪：hero 1014 是 1351432）。
  - `MethodInfo::methodPointer` 是首个成员（与现有 `il2cpp.cpp` 的取法一致），`method_from_name`
    之后直接取首字段即可。

## 验证

- 契约测试 `test_bridge.c`：断言看板娘 1014 → `DubbingId` 1351432、且二次调用不重复播放
  （`MainAniEnter` 每次回主界面都会跑，只有登录那一次该出声）。夹具按真实表值构造，覆盖
  「同英雄但非标题行」与「标题行但非本英雄」两种跳过。编译并运行：

  ```sh
  clang --target=x86_64-linux-android24 -O1 -Wno-unused-parameter \
      -Wno-gnu-variable-sized-type-not-at-end \
      -o test_bridge_x64 tools/savemanager/client/test_bridge.c
  adb push test_bridge_x64 /data/local/tmp/ && adb shell /data/local/tmp/test_bridge_x64; echo $?
  ```

  实测 exit=0，其中既有存档管理用例同时通过，即同库新增函数无回归。
- `patch_title_voice.py` 在本包 `libil2cpp.so` 上跑通：自动定位 cave 0x429f630、`dlopen`/`dlsym`
  PLT 桩 0x113efd0 / 0x1140230，被搬移指令 `stp x20, x19, [sp, #-0x20]!` 还原后 `b #0x13be1d8`
  回原函数，hook 与 cave 之外无字节变化。
- 播放逻辑（按 `(HeroId, 标题)` 查表 → `PlayVoice`）在改包客户端 + 本地服上实测出声，logcat 打出
  `login title voice: hero=1014 dubbing=1351432 played`。该路径走的是本仓库以外的自有 hook，
  **本 PR 的跳板本身未在官方 2.4 包上端到端跑过**——请打补丁后先核对 `MainAniEnter` 首字节与
  cave 内容，再实机验收。
- 未改动 `validate_unsigned_apk.py`：该脚本的 `HOOK_OFFSET`／cave 字节只对本包存档管理跳板成立。
  标题语音跳板的校验由 `patch_title_voice.py` 内建完成；若要并入管线校验，把本包 RVA 与 cave
  地址填进该脚本即可。本 PR 未生成任何 APK。

## 版本约束与待办

- `--rva` 只对已核对的 `libil2cpp.so` 成立。请以本包 dump.cs 里 `MainHallFSM.MainAniEnter`
  的 RVA 重新生成，并核对方法首字节与已有补丁（存档管理 cave 在 0x42B02C0），两份 APK 各自核对。
- 打包顺序：`build_bridge.py`（libx2save.so，含本函数）→ `patch_title_voice.py`（libil2cpp.so）
  → 原有签核流程。


## 2026-10-24 当前发布包补修

本次2.4基线的真实MainAniEnter为0x13BDA24，前三条原指令为f44fbea9 fd7b01a9 fd430091；不能套用上文其他构建的0x13BE1D4。新跳板保留x0–x30、q0–q31及NZCV/FPCR/FPSR，桥内处理libx2save句柄无法解析il2cpp API时的回退。当前PLT为dlopen=0x113E820、dlsym=0x113FA80，由ELF导入表定位。实际字节在ARM64仿真中验证成功和两种失败路径，C契约测试通过；尚未进行当前签名包的实机音频验收。详见docs/savemanager/CLIENT_RELEASE_20261024.md。
