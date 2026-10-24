# 客户端修复发布 2026-10-24

## 交付

两包均保留原服务器地址、包名、签名身份及既有存档管理、活动入口/经营和分配器修复；未自动安装覆盖模拟器。旧 ActivityUI 两包保留用于回退。

| 包 | 地址 | SHA256 |
| --- | --- | --- |
| D:/demo/x2/逆向/打包/X2-Revival-ClientFix20261024-Local-signed.apk | http://10.0.2.2:18080 | 9473d1c5e3f030c4885d66157c3f9b34f6f57d5dfbe119becd0de6859a0e3cf2 |
| D:/demo/x2/逆向/打包/X2-Revival-ClientFix20261024-Remote-signed.apk | http://8.163.2.72:18080 | cf023ea51f9d65b6b12227ef3417795b70c21e21c279c2b26b27c2310b3c95ea |

每包2147362643字节，低于旧版Unity工具链2GiB-1上限。静态立绘纹理缩至1361×1408，MainPaintingScale=80补偿显示尺寸，头像保留150×150。原立绘PNG不修改。

## 六项修改与边界

1. DailyDungeon 2030500/2030600/2030700/2031200（饕餮、阿波菲斯、惩罚者、天枢再临）七天OpenTime均为1，开放说明复用每日开放文案。保留等级、前置和关卡数据；服务端原有always_open逻辑一致。
2. 主界面四个赛季入口分支统一使用原包起源悖论入口Sprite，隐藏其他赛季文字组件，保留控件身份和点击回调。赛季主界面仍使用官方UI_BattlePass_Main；共享战斗选择页加入同一官方起源标题，使用原包蓝色城市场景作为兼容背景，替换后续赛季背景/底部装饰。兼容背景不是声称找回的原版起源战斗背景。当前只恢复起源，未来新赛季需配套切换美术。
3. 静影糜株按用户答复只恢复静态立绘：头像、卡面、资源索引与UnitBase外观列表齐全，Appearance.SpineShow清空以使用正常静态分支；没有伪造骨骼动画。使用PR67既有兼容立绘，原画出处未独立确认。货位1980045默认开放；旧客户端可用X2_IZANAGI_SKIN_PATCHED=0隐藏。使用该货位应配套新APK。
4. 合入PR69并补修：当前包MainAniEnter真实地址0x13BDA24（PR示例0x13BE1D4来自其他构建，不能沿用），原始前三条指令校验。跳板保留x0–x30、q0–q31、NZCV/FPCR/FPSR，随后执行被搬移的原指令并回原函数。修复dlopen所得libx2save句柄不能解析引擎API的情况，桥内回退打开libil2cpp。按看板英雄和标题语音表行定位并播放，每进程首次主界面补播一次；切回主界面不反复播。
5. IdentifyItem 0x1E497D8的原比较移入安全代码区。仅ItemType=10（兽主）且w26=0（六星鉴定档）从roll<129改为roll<385，保持Range(1,cap)随机调用及所有等级/MF/掉落组修正，精确得到min(3*p6,1)。其余星级条件公式不变，但因六星更易命中，继续向低星鉴定的总次数自然减少。非兽主不变。例：等级302、需求10、MF0、Cv0时六星约0.33004%→0.99012%。这是每次鉴定概率，受掉落组候选、地图星级范围和预算限制，不等于每关六星件数保证翻三倍。
6. 审核46个已补图背景节点，保留现有Sprite绑定（包括活动专用图和先前兼容CG）；修复6处单轴为0的固定锚点RectTransform：newyear2_main/790、newyear2_section/1684、newyear_main/491、sakura_main/306、zhenxun_section/906、osiris_section/1012。原补丁仅处理宽高同时为0，遗漏这些节点。背景不拦截点击。秘宝之海仍关闭，未恢复其玩法；也未把全部CG绑定宣称为官方原图恢复。

## 验证

- 两包v1/v2/v3签名验证通过，证书SHA256 c30b8137ce4ccd8103d2c940ea7690db9df9b6bb99117ddfa9a9f11223642c28，与原发布身份一致。
- 两包完整ZIP CRC、4字节对齐、修改白名单通过；除签名外各修改16条目。原GameConfig字节不变，classes5.dex和libunity.so字节不变；存档管理入口继续存在。
- Unicorn运行实际补丁字节：150组物品类型/星级/随机数分支，51199种随机分母的三倍概率关系，语音成功/dlopen失败/dlsym失败三条路径寄存器与状态保持均通过。
- 桥接C契约测试通过；外观商店及外观功能回归通过，另覆盖1980045扣费、到账、HeroSkinAll同步与重试不重复发放。测试均为隔离临时库。
- 本地服务已备份后重启；未修改玩家存档、未部署远程主机。界面、音频和真实战斗掉落的实机验收交由用户，不将包/仿真校验等同实机验收。

审计文件：analysis/client_release_20261024/。APK与运行时构建文件不进入Git。

## 可复现入口

- tools/savemanager/client/patch_client_release_20261024.py：从已有ActivityUI包生成原生、资源和静态外观补丁。
- tools/savemanager/client/build_bridge.py：构建保留存档功能的语音桥。
- tools/savemanager/client/rebuild_existing_apk.py：按manifest打包；构建器缓存重复压缩结果，未变条目复用已有压缩数据。
- 原签名工具：D:/demo/x2/逆向/脚本/sign_release.ps1，仍使用原发布证书和签名后大小检查。
- tools/savemanager/client/validate_client_release20261024.py：需要隔离安装unicorn（本次2.1.4），执行ARM64验证。
- tools/savemanager/client/validate_client_release_archive.py：最终安装包CRC、配置、资源、对齐及大小验证。
