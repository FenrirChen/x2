# 活动图片二次复查（2026-10-11）

## 结论

不能把活动页面的 Sprite 空引用直接解释成「APK 没有对应图片」。上一版 39 页的 55 处补图使用兼容 CG，只解决缺图显示，并未恢复每个页面的官方原始绑定。本轮确认包内还有活动专用背景、章节图及地图组件；部分原页面已有正确引用。对于其余空节点，目前仍未确定其原本绑定，不能声称图片彻底丢失。

本轮只分析资源并更新记录，没有修改 APK、生产代码或玩家存档。

## 扫描范围与限制

来源：`D:/demo/x2/X2_Eclipse_v2_4.apk`。

- 7922 个非拆分 Unity SerializedFile 全量元数据扫描，无解析错误。大图筛选得到 754 个 Sprite、1066 个 Texture2D；这是对象数量，同一张图可同时有 Sprite 和 Texture 对象。
- 补查全部 Sprite/Texture 名称，未仅依赖 ResourceManager 的 5272 条索引；找到 66 个带活动主题及背景类名称的对象，包括小型面板/图标。
- 合并并解析 36 组 `.split` 文件，无解析错误，检查媒体清单。
- 检查活动预制体的 396 个直接外部依赖；找到 14 个大 Sprite，并记录引用它们的页面。
- 解开特效 AB 的前置字节后，检查斟鄩、冬至 UI 特效，以及 `pack/ui.ab`、`pack/texture.ab`、`pack/zhenxun.ab`、`pack/gonggong.ab`。后四包含 2139 个媒体对象，主要为特效、模型贴图。未把这些贴图认定为缺失页面的完整背景。
- 原包视频文件名检索仅找到 `assets/Video/PV.mp4`；这不排除动态下载内容、无主题名称资源或游戏场景生成的背景。
- 资源名、主题相符及图片可解码均不能单独证明官方页面绑定；已有 PPtr 引用才是本轮确认的页面证据。也未声称已逐张目检全部纹理或扫描 APK 每一个 AB。

## 已确认的页面引用

| 图片 | 尺寸 | 原版引用页面 | 判断 |
| --- | --- | --- | --- |
| Ying_Mian_BG / Ying_Mian_BG2 | 1688×1004 | ui_sakuraend_main | 樱之岛后篇主背景实际存在；前篇 ui_sakura_main 的两个背景节点仍为空，不可混淆前后篇 |
| YingZhiDao_FuBen_BG | 2048×892 | ui_sakura_section / ui_sakuraend_section | 樱之岛关卡背景实际存在且已有引用 |
| YingZhiDao_ShangDian_bg | 1628×752 | ui_sakura_shop / ui_sakura_task | 樱之岛商店及任务相关背景实际存在 |
| Ying_RenWu_BG | 1628×752 | 见引用清单 | 樱之岛任务背景实际存在 |
| YueXiChuJiu_RiYueBG | 1336×752 | ui_yuexichujiu_main / ui_yuexichujiu_reprint_main | 日月盈仄主背景实际存在且已有引用 |
| ChuJiu_HuoDongBG / ChuJiu_JuQingBG / YueXiChuJiu_JuQing_BG | 1336×752 / 1024×512 | 见引用清单 | 活动及剧情页面背景实际存在 |

完整文件哈希、PathID、页面引用见 `analysis/activity/original_background_references_20261011.json`。

## 可用但不能直接当作全屏原背景的图片

| 活动 | 包内资源 | 使用限制 |
| --- | --- | --- |
| 阏逢敛遗 / 珠雀绮馔 | ChapterNewYear01、02、03；ChunJie_BGn；春节 CG | 章节图 964×752；ChunJie_BGn 是带「限时任务」文字的面板，非整个活动主界面背景；CG 官方页面绑定尚未恢复 |
| 斟鄩之邑 | ChapterZhenXun；zhenxun1 等 CG | 章节图与全屏构图不同；UI 特效提供粒子而非可直接替代的完整背景 |
| 秘宝之海 | ChapterZhouNian；AnniversaryMap_1～6；ann1 等 CG | 地图块为不规则组件；不可拉伸单块当作完整地图；章节图非全屏背景 |
| 全景裂隙 | ChapterOsiris；OsirisBG | 对应主题图片存在；并未恢复空节点的官方绑定 |
| 冬至万物 | ChapterGongGong；gonggong_scene / scene2 | 主题背景与章节图存在；章节图不能直接拉伸替代全部页面 |

Activity_NewYear2022、Activity_Anniversary 为按钮/标题等图集，经解码检查，不是漏掉的一张完整主背景。NewYearShop 是模型贴图，不能仅凭名字作为商店页面背景。

## 后续修复依据

已正确绑定的页面应继续使用其专用图片；如果仍白屏，需要检查加载和显示链，不能覆盖为统一 CG。空引用页面需要继续区分前后篇、主界面、关卡、商店、任务及小游戏；章节图和地图块应按原用途使用。无法确认原绑定时，兼容图要继续明确标注，不冒称官方恢复。

候选图实物预览：`runtime/activity_original_candidates.jpg`。原始扫描清单及拆分/AB 分析在 `runtime/all_large_images.json`、`runtime/all_themed_background_names.json`、`runtime/split_media_inventory.json`、`runtime/activity_bundle_media.json`。上述 runtime 文件为可重建分析产物，不进 Git。

早期方案文档中的「尚未打包」是初次研究时状态；两份已打包版本的状态以 `docs/savemanager/ACTIVITY_ART_AND_SAVE_RELEASE_20261011.md` 为准。
