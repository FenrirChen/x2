# 导入备份保留与注册开关（2026-10-15）

## 导入备份

新备份位置为 `<数据库目录>/server_backups/save_import/player_<玩家ID>/latest.x2save`。备份的是本次导入前的玩家状态，不是上传文件，也不是整服数据库。

在存档导入锁内，先导出并校验当前状态，将临时文件完整写入、flush/fsync，然后以原子替换更新 latest.x2save。写入或替换失败则不开始数据库导入，旧备份保留；替换后数据库导入失败则数据库回滚，最新备份仍可用于恢复。多次并发导入串行执行。

服务启动时自动清理历史多余备份，以玩家ID及账号核对压缩包 manifest 归属，并在删除前验证保留文件可解析。正常历史备份只保留最新一份，下次导入后统一使用 latest.x2save。清理仅处理系统生成的文件名，跳过链接、归属不符、未知文件，异常写日志而不冒险删除恢复点。不要手工往此目录放其他档案。

导出不会写备份文件。import_audit.log 是审计日志，不是存档备份，仍追加记录。该逻辑不会清理运维整库备份。

## 注册实时开关

在服务器项目目录执行（数据库路径必须与服务使用的一致）：

```sh
cd /opt/x2
.venv/bin/python -m tools.registration close --database /var/lib/x2/player.sqlite3
.venv/bin/python -m tools.registration open --database /var/lib/x2/player.sqlite3
.venv/bin/python -m tools.registration status --database /var/lib/x2/player.sqlite3
```

close 关闭、open 开启、status 查询；默认开启。开关在 server_settings 表持久保存，每个注册事务内实时读取，命令成功后新的注册不再放行，已有账号登录不受影响。已先取得写锁的注册事务可能先完成，控制命令会等待其提交，再切换；命令不需要重启。该表属于服务器配置，不随玩家存档导入导出，也不通过旧档覆盖。

本地测试服的数据库路径为 runtime/phase14/player.sqlite3。
