# 活动背景与存档接口交付（2026-10-11）

## 安装包

| 用途 | APK | 登录地址 | SHA256 |
|---|---|---|---|
| 远程服务器 | `D:/demo/x2/逆向/打包/X2-Revival-ActivityArt-Remote-signed.apk` | `http://8.163.2.72:18080` | `244b3e5a260abdf7a57f1ef866f9ebead22abd59d5ab38462e5789435bbc094a` |
| MuMu 本地开发 | `D:/demo/x2/逆向/打包/X2-Revival-ActivityArt-Local-signed.apk` | `http://10.0.2.2:18080` | `8f9cbd19dec3884f93b10c5afcc2b776d668b62340c4e8f43ee6ba97a48d1ba1` |

两包均为 2,144,913,235 字节，沿用原发布证书，v1/v2/v3 验证通过。
这两份使用同一个 Android 包名与证书，属于可相互覆盖安装的环境版本。
本地地址用于 MuMu 访问 Windows 主机，不是手机连接局域网的地址。
2026-10-11 实测 `fenrirchen.com` 解析为 `8.163.2.72`。

## 背景修复范围与性质

39 个 prefab、55 处原本为空的背景 Sprite 引用；39 个资源文件及一份
GameConfig 是相对 AuthFix 包的全部内容变化。存档管理 AuthFix/native bridge、
classes5.dex、libunity 分配器修复保持一致。遮罩、按钮、小型白色面板不作自动替换。
零大小的背景 RectTransform 补齐显示尺寸，背景不拦截点击。

这些是使用 APK 已有图片的**兼容配置**，不宣称恢复了丢失的官方美术对应关系。

| 活动/页面 | 使用的原包图片 |
|---|---|
| 阏逢敛遗、珠雀绮馔主页/关卡/商店/灯会 | `uialtas/cg/chunjiebg2` |
| 上述活动经营/食物制作页面 | `uialtas/cg/chunjiebg3` |
| 伪生樱之岛主页 | `uialtas/cg/yinghu` |
| 斟鄩之邑主页/关卡/商店/任务 | `uialtas/cg/zhenxun1` |
| 秘宝之海主页/关卡/奖池/任务/塔入口 | `uialtas/cg/ann1` |
| 全景裂隙主页/关卡/商店/任务/塔 | `uialtas/cg/osirisbg` |
| 冬至万物主页/关卡/商店/任务 | `uialtas/cg/gonggong_scene` |
| 日月盈仄，以及其他已绑定背景的页面 | 保留原有绑定 |

完整对象清单在构建输出 `tools/savemanager/client/build/activity_art/background-audit.json`。
可复现脚本：`tools/savemanager/client/patch_activity_backgrounds.py`，输入索引为
`tools/savemanager/client/activity_resource_index.json`；UnityPy 依赖在父目录 `.phase2_deps`。
构建器 `build_apk_savemanager.py` 增加可选第三个参数：资源补丁 manifest。
两份 GameConfig 经解密重读确认仅修改生效行的 Login_Url。

## 服务端

18080 bootstrap HTTP 服务提供以下 POST 接口：

1. `/save-manager/auth`：现有账号/密码验证，发放 600 秒专用存档 token。
2. `/save-manager/status`：查询账号在线状态。
3. `/save-manager/export`：Bearer token 验证后返回该账号 `.x2save` 二进制容器。
4. `/save-manager/import`：离线导入，导入前备份、单事务恢复，成功后撤销存档 token。

存档 token 与游戏登录 token 分离，未授权导出返回 401。在线状态获取失败返回
503，禁止继续覆盖存档。日志不输出密码或 token。

存档 schema 更新为 `x2-revival/3`，覆盖 83 张玩家状态表及 players.snapshot。
补齐活动、基地动作回执、无尽、预设、锁定、剧情回顾、待发奖励、世界 BOSS 等数据。
全服 BOSS 日历不随玩家导入；个人每日 BOSS 实例通过个人每日记录归属导出，
全服共享实例不随某个玩家导入覆盖。账号认证数据、运维修复历史不导出。
旧 schema /2 文件会明确拒绝，避免按旧边界静默丢弃新增玩法状态。

修复旧 ZIP 128 条目限制：实际测试账号已有 1104 个 BLOB，旧限制会使服务器
无法读取自己导出的文件。现在条目上限 65535，同时保留 96 MiB 上传、
256 MiB 解压总量及逐项校验和等校验。扫荡奖励审计关联扫荡回执，不能只校验战斗 run。

核心文件：`src/x2server/player/save_manager.py`、
`src/x2server/bootstrap/save_manager_api.py`、`bootstrap/http_server.py`、
`bootstrap/local_identity.py`、`tools/local_game_server.py`。
审计索引和验证脚本在 `tools/savemanager`，本次逐表恢复证据在
`docs/savemanager/SAVE_ROUNDTRIP_VALIDATION_DATA.md`。

## 验证与部署状态

- 两份签名 APK 完整 ZIP CRC 通过，内容改动白名单精确为 40 项。
- 全部背景依赖 Sprite 可解析，并能解码出 1336×752 图像。
- 每个改动 prefab 重新读取确认引用有效，其他对象的原始序列化数据逐字节相等。
- 19 项存档单元与真实 HTTP 测试通过，含大于 128 BLOB 的恢复、失败在线检查、
  同账号恢复、跨账号导入、凭据保留与事务回滚。
- 真实 60 级测试存档在隔离 SQLite 副本中完成导出、恢复、canonical 全量比较：
  338,191 字节 / 83 张表 / 1104 BLOB，无差异；活跃数据库没有被导入覆盖。
- 本地服务器已备份后重启，HTTP 18080、游戏 29000、聊天 29001 正常监听。
  备份 `runtime/before_activity_art_save_20261011_094606.sqlite3`；
  启动日志 `runtime/activity_art_save_20261011_094606.err.log`。
- 本次未安装覆盖模拟器 APK，未进行逐页面客户端截图验收，以上为包与序列化验证。
- **远程服务器仍返回存档接口 404**。本次没有推送或部署远程；必须同步本轮完整
  服务端代码并重启远程服务后，远程 APK 的存档管理才能使用。
