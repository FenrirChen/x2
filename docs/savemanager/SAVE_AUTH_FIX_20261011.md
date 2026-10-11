# 存档管理入口修复（2026-10-11）

## 现象与结论

用户使用 `D:/demo/x2/逆向/打包/X2-Revival-SaveManager-signed.apk`，同一账号密码能正常登录，点击存档管理则立即提示账号密码错误，未出现导入/导出窗口。

旧实现存在真实客户端缺陷，先前报告的静态验证不足以证明入口可用：

1. trampoline 的 `dlsym` 参数顺序写反。应传 `(handle, symbol)`。
2. 传给桥的句柄属于 `libx2save.so`；桥现在自行打开 `libil2cpp.so`。
3. 桥调用多个不存在的 IL2CPP 导出名，如 `il2cpp_field_from_name`。已替换成实际存在的 `il2cpp_class_get_field_from_name` 等；全部 21 个依赖符号与客户端 `.dynsym` 对照通过。
4. `il2cpp_string_chars` 返回 UTF-16，不能作为 UTF-8 字符串传给 `il2cpp_string_new`。现在直接传递原有托管字符串，账号、密码和地址不经过错误转码。
5. Java `open(account,password,baseUrl)` 的参数数组原本还包含方法名，实际为四个参数。现在方法名独立传递，参数数组只有三个。
6. 桥失败不再执行游客登录。新增 `X2SaveManager` 阶段日志，不含账号、密码、token；Java 日志仅含接口路径和 HTTP 状态。

## 服务端现状（实测）

使用不存在的探测账号，不访问任何玩家存档：

- 本地 `POST http://127.0.0.1:18080/save-manager/auth` → HTTP 200，`code=invalid`（符合不存在账号的结果）。
- 线上 `POST http://fenrirchen.com:18080/save-manager/auth` → HTTP 404，`error=not_found`。

线上当前没有可用的存档认证路由，或该路由未被转发到支持它的进程。这与游戏 TCP 战斗请求是否成功无关。修复客户端后，接口 404 会明确提示「服务器尚未启用存档管理接口，请更新服务端」。本次没有部署线上服务器，也没有推进活动/玩法开发。

已有本地接口涉及 `bootstrap/save_manager_api.py`、`player/save_manager.py`、`bootstrap/local_identity.py`、`bootstrap/http_server.py`、`tools/local_game_server.py` 的装配及 `player/store.py` 的 `validate_snapshot`。新文件尚未纳入 Git，不能假设线上通过普通 pull 已获得它们；部署时还需要核对当前数据库与存档边界，不能只复制入口文件。

## 修复包

`D:/demo/x2/逆向/打包/X2-Revival-SaveManager-AuthFix-signed.apk`

- SHA256：`98df41d0f0dcb4710a9e97e0ebee403ceb93fd51b452e238cc19007b469127c0`
- 大小：2,144,999,251 字节，低于 2 GiB−1。
- 与旧 SaveManager APK 对照，除重签条目，仅改变 `libil2cpp.so`、`libx2save.so`、`classes5.dex`。其余条目 CRC 和条目集合一致。
- 原发布证书 SHA256 `c30b8137ce4ccd8103d2c940ea7690db9df9b6bb99117ddfa9a9f11223642c28`，v1/v2/v3 验证通过；`libunity.so` 的 allocator 修复保持原样。
- 原 APK 保留，未自动安装、未导入或覆盖玩家存档。

## 验证

- 原生桥 host 合约测试通过：正确句柄/API 名、三个原始托管字符串的传递、泛型与 void 重载选择、缺失 API 时返回失败、空页面失败。
- trampoline 反汇编校验通过：dlsym 参数、调用目标、正常返回、不回落游客登录。
- APK 全 CRC、语言文字、hook、dex、native lib、2,225 个 stored 条目对齐校验通过。
- 隔离库 HTTP 测试 5 passed：认证、导出/导入、在线导入拒绝、错误 token、游戏 token 隔离、实际 HTTP socket。修正原测试在服务器事件循环内同步发 HTTP 造成的死锁；服务端功能代码未修改。

尚未完成 Android 实机点击和 SAF 文件选择验收。线上 404 消除前，不能宣称线上存档导出/导入已经可用。
