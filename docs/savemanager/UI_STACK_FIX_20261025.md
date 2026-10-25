# 2026-10-25 空活动商店与返回主界面堆叠

## 复现与证据

用户路径：打开斟鄩之邑活动商店，商店为空，返回主界面后商店残留。ADB截图确认商店默认0000/0000及抽取按钮与MainPage同时显示。

只读读取UIManager实际实例，UI_ZhenXun_Shop实际类型为AncientBoxView；其UIBase.IsOpen=0、IsHide=0，但GameObject原生activeSelf=1。对象的静态奖池UI列表已有6项，而mCurPoolItem仍为空。UIManager虚方法表指向正确的AncientBoxView.OnOpen，排除创建了错误界面类型。

反汇编：AncientBoxView.OnOpen(0x17B9954)先调用ActivityNoticeModule.GetDefalutSelectId(0x133B518)，后者会对已解锁奖池ID缓存取Count-1；空缓存会索引-1。OnOpen末尾0x17B9B6C才发送ActivityRewardPoolInfo查询，形成先读缓存、后查询的循环依赖。初始化中断发生在UIBase将IsOpen置1之前，所以返回主界面时正常关闭流程不会处理这个半打开面板。故障现场未发送商店应有的奖池查询。

日志另有BattlePassTaskTab.Refresh(0x14C928C)两次空引用；该函数仅判断事件类型是否等于共享DailyTaskModule当前类型，并未限定赛季15，普通日常/周常事件也能落入赛季控件刷新。

## 修复

1. ActivityRuntime在活动目录应答、首次同步、轮换时主动下发当前活动真实已解锁奖池；在目录和缓存包之间隔开客户端派发批次。没有伪造奖励、库存或解锁状态。
2. 同步状态改为按玩家及实际TCP连接跟踪；新玩家、重新登录、重连即使处于同一周期也会同步，避免全服只有首个玩家获得初始化。
3. 客户端仅为BattlePassTaskTab.Refresh增加type==15门禁；每次正常赛季刷新仍执行原始函数，不按IsOpen字段过滤（这个字段实际用于首次滚动刷新，不能当可见标记）。
4. 本轮不修改通用UI管理器、不强行隐藏所有窗口。修复初始化依赖，保留原有页面开闭逻辑。

## 交付与验证

安装包位于D:/demo/x2/逆向/打包/：

- X2-Revival-UIStackFix20261025-JP-Local-signed.apk，SHA256 389135d362c84c35d0a6a7e642a6e027950931c25221038c9e946fc7ec273013。
- X2-Revival-UIStackFix20261025-JP-Remote-signed.apk，SHA256 5866dd202538385fbbeb5e2dbf4069760d6ae9fddd15cee69ad204296cbe962d。

每包2147166035字节，原证书v1/v2/v3验签通过。相对于JP基线仅libil2cpp.so变化，反和谐资源、赛季背景、存档管理、服务器地址及其他原生补丁均保留。

116项活动回归和5项TCP集成测试通过；任务门禁29种ARM64输入验证通过；原六星150项矩阵/51199分母及标题语音3条ABI路径验证通过。全部ZIP CRC/对齐及逐条变更范围校验通过。

本地APK于20:50:10覆盖安装成功，保留应用数据。服务端已于20:48:57备份测试存档后重启。远程服务器尚未部署；远程端完整修复需要同时更新服务端代码与APK。

## 安装后实机回归

2026-10-25 20:56–20:59，PID7425：活动→古代宝箱已显示真实商品、库存和阶段锁定状态；直接点击主城按钮返回后，没有商店面板残留。每日任务、赛季任务及反复切换均显示正常，未领取奖励或购买商品。该进程登录后Unity日志未出现NullReferenceException；启动SDK的JSON/设备ID权限警告仍存在，与本次Unity面板异常无关。截图及摘要在analysis/ui_stack_20261025。

边界：商店背景装饰仍有缺图，未将其认定为已修复；本次登录的活动海报入口需先打开另一个面板后才响应，原有首次点击不响应问题仍待单独修复。当前修复验证的是商店半打开残留及任务刷新异常，不能据此宣称所有UI堆叠来源均消除。
