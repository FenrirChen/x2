# 第三方包缺失资源引用对照（2026-11-07）

输入D:/demo/x2/x2(1).apk，比较对象为当前签名本地包D:/demo/x2/逆向/打包/X2-Revival-Local-signed.apk。只读APK，未安装或替换，不改服务端、存档或远程。

第三方包新增401个ZIP条目，其中386个Unity资源文件合计366802596字节。主要分布于activity02/03/04/05/06/07/09，以及season01的8个资源文件；另有活动视频。ZIP未压缩新增条目总计870953317字节，不等于APK最终体积差。

按当前活动背景补丁列出的页面逐一读取Image组件，在相同对象ID对照实际m_Sprite与externals，而非只比较文件名。完整结果与目标类型检查见analysis/third_party_resources_20261107/reference_comparison.json、all_image_reference_diffs.json、added_assets_inventory.json、validation_summary.json。范围是本轮列出的页面，不能外推整个客户端所有资源已修复。

存在大量原先为null、第三方已指向独立Sprite/Texture2D文件的组件：标题、按钮、遮罩、经营页面、背景等；并非只有CG。举例樱岛主界面对象306/313分别指向x2_activity07_bg_10d65a71013a5ae41bf7c7eac2239713.assets和x2_activity07_bg_3d97555c2107802488f03d28076d0a62.assets，Sprite ID=2。全景裂隙主界面374指向x2_activity04_ui_1.assets（AoXiLiSi_Main_BG）。已成功解码预览PNG保存在同目录。

可行迁移方案：以当前正式包为基线，只纳入所需新增Unity文件和引用，按第三方目标Sprite建立外部文件索引；对当前Image组件逐个修正引用，并核对尺寸、锚点、遮罩及点击穿透。保留现有半价商店、价格上限、做菜、存档管理、六星概率及原生函数修补，不覆盖第三方so/dex/AndroidManifest或整套预制体逻辑。资源管理器globalgamemanagers与加载依赖也须验证，不能只将.assets复制进去就宣称可用。

来源仅为第三方复原，尚无原服界面抓包或实机对照，不声称每张图的绑定都是官方原始配置。8个season01文件包含通用赛季图集、商店背景、玩法背景等，不能据此确认起源悖论主背景动态CG已完整恢复。当前只完成静态取证和引用计划，未打包、安装或运行游戏验收。

补充验证：39个活动预制体页面内331处图片引用变化，其中291处由空引用变为有效Sprite；331个目标均可在第三方APK解析到Sprite，未发现缺失目标。还找到我们当前包没有的assets/Video/battlepassMain.mp4，MP4头解析为1688×1004、2秒、1392250字节，已单独提取作候选。这与赛季动态背景用途相符，但尚未播放或实机核对具体画面和VideoPlayer绑定，不能直接认定为起源悖论官方动态CG。

## 授权后补包结果

以各自最新签名本地/远程包为基线，生成D:/demo/x2/逆向/打包/X2-Revival-Resources-Local-signed.apk与X2-Revival-Resources-Remote-signed.apk。每份2680713781字节。迁移58个资源文件、418处Image引用（其中原空引用数量详见release_summary.json），补386个Unity文件和9段StreamingAssets视频，合并88条资源绑定。保留旧externals索引，追加新索引；未触及的对象逐个字节验证一致。保留原有RaycastTarget修复。

赛季MediaPlayer原已配置Video/battlepassMain.mp4，现补文件并恢复DisplayUGUI 326，仅关闭旧静态Image 387。视频60帧/30fps，已实际解码帧，0与30帧差异均值11.7899，确认是动态画面。

两包均通过原发布证书及v1/v2/v3签名验证、全ZIP CRC、所有418个Sprite目标解析、媒体stored方式及4字节对齐验证。未列入迁移的条目保持CRC和长度一致，核心so/存档桥/DEX/服务器地址载荷逐字节保留，不继承第三方地址。报告为local_release_validation.json、remote_release_validation.json；构建工具5项测试通过。

打包器允许超过2GiB但仍检查ZIP32的4GiB/65535条目边界；使用原签名密钥。保留旧签名成品作回退。没有安装新包、未宣称已通过游戏内全部活动验收，待用户手动验收；未推送或操作远程。
