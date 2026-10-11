# 日月盈仄剧情入口与主城白图修复

## 服务端证据与处理

日志 `activity_ui_followup_20261011_230107.err.log` 中玩家 5 的 686 查询及多次 628 请求均被以 `no food dialogue` 拒绝。原分支只接受餐厅类型 27，实际日月盈仄使用序章类型 1。

原版客户端 `YueXiModule.Show`（0x22A95B0）先检查 `CheckNoticeCanAward`，满足条件就播放 `ShowStory`；`ShowStory`（0x22A9C84）以活动开始后的天数索引 Param1 剧情。`OnPLotEnd`（0x22AC810）在完成或跳过剧情后发送 628。629 成功处理器（0x22AC980）更新 LastReceiveTime、展示奖励并保存本地已读次数；686/687 则在初始化时恢复领取时间。原配置 70009 的 Param1=[1942001]、Param2=[776004]，只保留了一天序章。

修复为返回原表奖励并保存本期序章领取时间；与通用预告领奖共用状态，跨协议不能重复领奖。同请求重放沿用事务回执，不重复发奖。下一轮状态重置。序章只开放原表保留的天数，并按客户端北京时间日切关闭；主活动和商店仍开放五天。活动监视器会在序章关闭时推送入口状态，避免在线跨日继续尝试不存在的第二天剧情。

## 客户端图片

APK 的 `assets/bin/Data/level2` 主城场景中，`mYueXiEnter` 开放／锁定两组的 Human、Fox、Des、Mark 共八个 AdvancedImage 的 Sprite 引用全为零。图片为空时 Unity 会画出截图中的白色矩形。

`patch_yuexi_hall_icon.py` 将两组 Human 绑定为包内 `YueXiChuJiu_Icon`（文件 8281f30dbfa6b4341b686850c542e747，PathID 15），Des 绑定为 `YueXiChuJiu_RiYueYingZe`（PathID 27），保留长宽比例。其余空 Fox／Mark 禁用图形组件，保留对象、动画结构、点击区域及红点。这是使用现有官方标题与徽标的兼容显示，不声称还原人物／狐狸原条幅。

两份发布包继续使用 `X2-Revival-ActivityUI-Local-signed.apk` 和 `X2-Revival-ActivityUI-Remote-signed.apk`。与此前版本比较，除签名外仅 level2 的八个图形节点及新增 Sprite 外部依赖改变；所有其他场景对象、资源、DEX、native 修复和服务器地址均保留。验证 v1/v2/v3 签名与已有证书一致，zipalign 4 字节对齐通过。图片修复需要更新 APK，剧情链修复需要更新服务端。

## 验收范围

活动运行时、轮换和商店回归检查，以及序章完成／跳过、重新登录、跨协议防重、跨日关闭和下一轮重置测试。实际游戏界面由用户手动验收。

目前开放顺序为阏逢敛遗、伪生樱之岛、斟鄩之邑、全景裂隙、冬至万物、珠雀绮馔、日月盈仄。前六项已获用户通过，日月盈仄为最后一个待验收项。秘宝之海已按用户要求停用，不算验收通过或待开放。
