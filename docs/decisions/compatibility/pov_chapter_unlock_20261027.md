---
Document-Type: Compatibility Decision
Domain: Server / Client / PointOfView
Status: ACTIVE
Updated: 2026-10-27
---

# Decision

恢复星图「剧情回顾 / 前情回顾」(POV，`SectionType 4 = E_PointOfView`，关卡 212xxxx)
的整章解锁与通关奖励。**服务端 + 客户端都要改**：

- 服务端（本 PR 主体）：
  - 新增 [activity_rotation_extra.json](../../../src/x2server/data/activity_rotation_extra.json)，
    把客户端 `SectionTable/POVChapterInfo` 的完整 21 行（17 个常驻章节 + 4 个
    70010 活动章节）补回 `catalog['tables']`；
  - `ActivityRotation._supplement()` 在加载生成目录后合并这份补充表；
  - `ActivityService` 新增 `STATE_PERIOD = -1` 与 `pov_namespace()`：常驻章节的
    通关进度放在固定哨兵 period，活动章节只在 70010 档期内记进度/结算；
  - `pov_chapter_rewards()` 改为按章节命名空间记账，整章 `ClearReward` 只发一次。
- 客户端（**必须另打补丁，见 Usage**）：新增
  [patch_pov_favor_gate.py](../../../tools/savemanager/client/patch_pov_favor_gate.py)，
  把 `ChapterModule.GetFavorLevelByHeroId` 换成 `mov w0,#99 ; ret`，越过 POV 章节列表
  的神格默契度门槛。

# Reason

1. **客户端门槛**：`PovMapTab_RefreshChapters` / `RefreshSingleChapter` /
   `ChapterModule_CheckPOVChapterOpen` 用
   `GetFavorLevelByHeroId(heroId) >= POVChapterInfo.FavorLevel` 判断章节是否开放。
   `POVChapterInfo.FavorLevel` 常驻章节是 3（2021002 是 5），而新账号对这些 POV
   英雄没有默契度，正常要送很多周礼物才够，于是所有常驻章节一直锁着。解锁后星图
   才会出现「剧情回顾」的许愿币入口（`ChapterInfo.ReviewUnlocAward = 760066`）。
2. **服务端缺表**：`tools/analysis/export_activity_rotation.py` 生成
   `activity_rotation_catalog.json` 时只保留 `UnlockActiviyID == 70010` 的 4 行
   （第 88 行），17 个常驻章节根本没有进目录。原 `pov_chapter_rewards()` 又要求
   `self.rotation.activity(chapter['UnlockActiviyID'], period)` 命中当前档期，常驻
   章节连字段都没有，所以它们的整章 `ClearReward`（734000/734011/734500/…）永远
   发不出来；而 `period is None` 的提前 return 还让活动开始前完全无法结算。
3. 进度不能挂在每周轮换的 period 上：`activity_state` 以 `period` 为主键，档期一换
   常驻章节的 `pov-clear` 就归零，整章奖励可以反复领。哨兵 period 解决了这一点，
   且不新增任何表结构/存档字段。

入场校验**不需要**改：`battle_entry.resolve()` 本来就放行 `SectionType 4`
（`SECTION_TYPES[4] = "PointOfView"`，cost = `ManualValue`），89 个 Type 4 关卡都能
正常进场；通关记录也已在 `mission_values()` 里按 `(Type, ChapterID)` 产出 Type 4
pair，客户端据此画星图进度。

# Scope

服务端（无 schema 变更，`activity_state.period = -1` 复用现有表）：

- `src/x2server/data/activity_rotation_extra.json`（新增，21 行，含 `_source` 说明）
- `src/x2server/player/activity_rotation.py`（`_supplement()` + 合并）
- `src/x2server/player/activity.py`（`STATE_PERIOD`、`pov_namespace()`、
  `pov_chapter_rewards()`）
- `tools/analysis/export_activity_rotation.py`（注释，说明常驻行由补充表恢复）
- `tests/unit/test_pov_chapters.py`（新增，6 个用例）

客户端（只动 `lib/arm64-v8a/libil2cpp.so` 的 8 个字节）：

- 2.4 APK 内的 so：88855552 字节，
  `sha256 3b45b697c840c25d1c729c2f8b80e11b34093bdb9b90f48ac6134388b0259458`
  - `ChapterModule.GetFavorLevelByHeroId` RVA `0x16C7E14`
  - 原前 8 字节（`A9BE4FF4 A9017BFD …`，8 词完整比对）改成
    `mov w0,#0x63`（`0x52800C60`）/ `ret`（`0xD65F03C0`）
  - 补丁后该函数的 27 条指令（含尾调用 `FavorModule.GetFavorLevel_1`）除前 8 字节
    外**逐字节不变**，脚本会在写盘前反汇编校验，改到 entry 以外直接报错
- 全库扫描 `bl 0x16C7E14` 的调用点恰好 3 个，与上面三个 POV 判定一致：
  `0x15C2AEC`（`PovMapTab_RefreshChapters` 调用点）、`0x15C2F20`
  （`RefreshSingleChapter`）、`0x16B9FC8`（`ChapterModule_CheckPOVChapterOpen`）
- `work/apk` 下的 so 是另一构建：88872784 字节，`.text` 偏移 `+0x7B0`，
  同一函数在 `0x16C85C4`，已用 `--entry` 结构校验跑通

# Official

NO（常驻章节的默契度门槛是官方设计；服务端缺 17 行是导出脚本的取舍，不是官方行为）

# User-authorized

YES（USER_DECISION，2026-10-27）

# Usage

服务端：正常部署即可，无迁移、无开关。唯一可见差异是 POV 关卡通关后的整章奖励。

客户端（**这一步老大那边必须做，不打补丁 POV 章节仍然锁着**）：

```powershell
# 1. 从 APK 取出 lib/arm64-v8a/libil2cpp.so
# 2. 先确认地址（第二个参数在 --callers 模式下不写文件，给任意路径即可）
python tools\savemanager\client\patch_pov_favor_gate.py <libil2cpp.so> unused.so --callers
#    期望：callers of 0x16C7E14: ['0x15c2aec', '0x15c2f20', '0x16b9fc8']
# 3. 打补丁
python tools\savemanager\client\patch_pov_favor_gate.py <libil2cpp.so> patched.so
#    期望：GetFavorLevelByHeroId @ 0x16C7E14 (exact body) -> mov w0,#0x63 ; ret
# 4. 把 patched.so 按原条目名 lib/arm64-v8a/libil2cpp.so 替换回 APK
# 5. 用本地开发密钥重新签名后才能安装（签名步骤不在本工具内）
```

- 换别的构建（不是 88855552 字节这版）：从该构建的 `dump.cs` / `script.json` 查
  `ChapterModule.GetFavorLevelByHeroId` 的 RVA，然后
  `--entry 0x16C85C4` 这样显式传入。脚本会先做 27 条指令的结构校验（字段偏移
  `[x0,#0x10a]`、`[x0,#0xbc]` 是 il2cpp 对象字段，跨构建稳定），对不上就报错不产出。
- 只想复核、不想改：`--callers` 会先校验函数体再列调用点。

# Notes

- **不要**改 `FavorModule.GetFavorLevel_1`（`0x1AA543C`）：纸鹤页、头像、通讯录、
  送礼等级判定都直接调它，谎报等级会让这些页面显示错误。补丁只改
  `ChapterModule` 里那层 POV 专用 wrapper。
- 活动章节（2021023/2021511/2022711/2022811，`UnlockActiviyID = 70010`）只在
  「日月盈仄」档期开放；其他档期调用 `pov_chapter_rewards()` 直接跳过，不记进度。
- 整章奖励只在 `StageID` 全部**真实通关**后发一次；开发解锁工具写入的
  `economy_clears.first_uuid = 'unlock'` 只代表已解锁，不会触发 `ClearReward`
  （`pov-clear` 与 `economy_clears` 是两套账本）。
- 剧情回顾的「解锁」按钮走 `C2L_UnlockStory`（扣 1×1237916，给 760066），
  这条链路服务端已有，不需要本 PR 改动。
- 图五 `3月13日 - 4月10日 / 剩余-18826天` 的日期来自客户端 `OpenCycle` 静态表，
  不在本 PR 范围（已确认放弃）。
- 验证：
  `python -m pytest tests/unit/test_pov_chapters.py tests/unit/test_activity_rotation.py tests/unit/test_economy.py -q`
  → 49 passed；`tests/unit/test_activity_runtime.py` / `test_activity_protocol.py`
  一起跑共 136 passed。`tests/unit/test_battle_entry_domain.py` 有 3 个用例在 base
  `6aafdcd` 上就已经失败（2190001 / Origin Paradox 等级门槛、1203511 额外掉落），
  与本改动无关，已在干净 base worktree 复现。
