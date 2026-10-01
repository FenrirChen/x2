# 皮肤应用类型修复

线上 0214224 的 player=1 只保存 hero=1028/type=3/skin=1222804，
最近入场回包 battleSkinId 均为 0。本地同角色同时有 type=1 和 type=3，
所以错误类型解释被本地已有的局内记录掩盖。

客户端 ARM64 证据：

- HeroMainSkinSubPage.OnMBtnApplyClick 0x190b064：同步 Toggle 开启时，
  0x190b1b4 设置 w3=3，再调用 HeroSkinModule.SendApplySkin。
- 非同步分支 0x190b1d8/0x190b1dc 选择 1 或 2；
  HeroSkinPage.OnMBtnApplyClick 0x191dc38 同样选择 1 或 2。
- SendApplySkin 0x190b208 的 0x190b2c0 将 w3 写入 C2L_HeroWearSkin.type。
- HeroSkinModule.GetCurHeroSkin 0x190ae6c 的 0x190afa4..0x190afb4
  通过 isFight 选择 HeroSkin.battleSkin (+0x20) 或 outerSkin (+0x24)。

正确语义：type 1=局内，2=局外，3=两者同步。旧实现错误地只接受 1/3，
把 3 保存并回传为局外，而战斗只读取 1。

新请求 type=3 在同一事务写入 1/2 两槽，不创建 type=3 数据；type=1/2
只更新相应槽位。HeroSkinUpdate 先于成功回包，包含两槽实际状态。
皮肤所有权和角色归属校验保持原逻辑，失败不修改任何槽位。

启动时迁移旧 type=3：只补齐缺失的 1/2 槽，然后删除错误 type=3 行。
旧表无时间戳，不能判定已有独立槽与旧同步行的先后；保留已有独立选择，
不猜测覆盖。对于线上仅 type=3 的存档会完整恢复局内和局外皮肤。
迁移不创建皮肤库存、不解锁新皮肤、不改写历史战斗回执；新入场读取新状态。
本地启动前通过只读在线 SQLite 备份保护存档；线上部署脚本同样先备份。
