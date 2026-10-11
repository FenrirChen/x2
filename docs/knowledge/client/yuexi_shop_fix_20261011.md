# 日月盈仄商店空白修复

## 证据与原因

2026-10-11 23:25 的服务端日志显示，684 / C2L_ActivityShop 正常返回
code=10、3591 字节。Unity 日志在 `FestReprintShopView.ShopItem.SetShopIcon`
连续报空引用：当前加载的 `Table/ShopConfig` 缺少 887–890 四个商店。
保留的 `Table_410/ShopConfig` 中存在这四行，且字段布局与当前版本一致。

## 修复

`tools/savemanager/client/patch_yuexi_shop_config.py` 从旧表恢复四行，合并到当前
ShopConfig，保留原有 25 行的原始字节。商店图标、名称、排序和商品组沿用原表。
四阶段碎片门槛改为已批准的 6 / 12 / 18 / 24，与服务端购买校验一致。

合并后的表为明文 protobuf。原表使用 RSA/XOR 加密，不能在没有私钥的情况下
重新签出相同格式；因此在 `LogicX2.Resources.ConvertDataBytes` 的入口
0x1B4A0C4 跳转到 0x42B0D00，仅对匹配本表前 16 字节、长度至少 16 的数组
保留原始数据。其他数组继续执行原解码路径；保持 ref byte[] 参数和原栈帧。
未改动账号认证或奖励、购买请求处理。

服务端目录同步加入四行；`export_activity_rotation.py` 支持从保留表重建它们，
避免以后重新导出丢失。现有商店的购买扣料、限购、每期重置规则保持原实现。

## 验证与发布

- 原有 25 行字节一致，新增四行仅修改碎片门槛。
- 导出器重建的 29 行与服务端目录完全一致。
- ARM64 反汇编确认入口、长度检查、两次前缀比较、正常解码回退与返回地址。
- 原生库仅改变入口 4 字节和代码洞 88 字节，保留之前所有补丁。
- 活动商店回归 38 项通过；新增客户端/服务端门槛一致性测试 1 项通过。
- 两份 APK 仅修改 ShopConfig 和原生库；其他非签名条目完整保留，签名及对齐通过。

发布继续使用 `X2-Revival-ActivityUI-Local-signed.apk` 与
`X2-Revival-ActivityUI-Remote-signed.apk`。本地版覆盖安装，服务端重启。
视觉、实际收集碎片后的解锁及购买由用户手动验收。远程玩家需要更新 APK，
仅更新服务端不能补上客户端缺少的表行。
