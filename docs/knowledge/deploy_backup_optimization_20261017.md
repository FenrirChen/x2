# 部署备份流程优化（2026-10-17）

旧脚本在 pip 成功后静默执行 chown -R、在线一次性全库备份和 integrity_check，最后才重启服务。慢磁盘下的整库读锁可阻塞游戏提交，并触发已在 f22c86e 修复的事务泄漏。128MiB 临时库实验中，整库复制产生 6 次并发写入超时；分块复制允许写入但出现 4 次进度回退，因此本次采用先停服再备份。

## 新流程

1. 预检 Python、flock、timeout 等依赖及路径；已有 EnvironmentFile 中的 X2_DB_PATH 必须与要备份的路径相同，否则拒绝，防止备错库。
2. 持有按数据库路径命名的 flock，从更新代码到健康检查结束，第二个部署立即拒绝。锁文件可以一直存在，以实际文件锁为准，不需要手动删除。
3. git fast-forward、安装 Python 包；此阶段失败不会主动停止旧服务。
4. systemctl stop，最多等 120 秒，并检查 ActiveState=inactive/failed 且 MainPID=0。仍存活则拒绝备份。
5. 仅修正数据目录、runtime/logs 顶层目录及活跃 DB/WAL/SHM/journal 文件的所有者，不再递归扫描所有历史备份和日志。
6. 新备份工具只读打开原库，每次复制 256 页；复制后保留完整 integrity_check，不改成 quick_check。
7. 先以排他方式创建 .partial 文件，校验与文件 fsync 成功后，以同目录硬链接原子发布最终 .bak 名称，拒绝覆盖任何现有目标；旧备份不自动清理。最终文件名附加进程号，避免同秒覆盖。
8. 安装服务单元、启动服务，按原 3 个端口检查健康。仅所有步骤成功时打印 Deployment healthy。

## 进度与期限

每个阶段输出时间、阶段名。备份即使某一步很慢，也由独立心跳线程每 5 秒输出 stage、remaining_pages、total_pages 和耗时。复制结束、完整校验开始、校验成功分别输出；只有已发布的已校验文件才输出 DB_BACKUP。

备份/校验默认协作期限 600 秒，外层 GNU timeout 660 秒（额外 10 秒强杀宽限）；停服期限 120 秒。SQLite 操作和复制回调检查期限，integrity_check 使用 SQLite progress_handler 中断。真正阻塞在 Linux 不可中断 D 状态的 I/O 无法由用户态保证在期限内退出；进度输出有助于区别复制、校验和磁盘等待，不声称修复云盘硬件性能。

任何失败都返回非零、显示阶段、行号和原提交，不继续启动或误报成功。不会自动恢复数据库或回滚 Git。若已停服且备份失败，服务保持停服；若启动后健康检查失败，则保留实际状态供 systemctl 排查，不声称一定已停止。进程被硬杀时可能保留 .partial，它不是已校验备份；不会自动删除旧备份或正式 DB。

## 使用

用户此前运行 /root/deploy_server.sh 的副本。副本不会因仓库更新自动变新；推送后请改为运行仓库脚本：

```bash
cd /opt/x2
git pull --ff-only
sudo bash /opt/x2/deploy/deploy_server.sh
```

本轮不自动推送或操作远程服务器。仍使用 main、现有数据路径、环境文件和端口，不覆盖玩家存档。部署期间会中断游戏连接，停服窗口包括备份、校验和新服务启动。

## 验证

- 真实 SQLite：完整内容一致，原文件不变，WAL 已提交内容包含、未提交内容排除；拒绝覆盖最终备份或历史 partial；损坏源库和复制后的完整性检查失败不发布成功；锁等待有期限，解除锁后可重新备份。
- 实际 Git Bash 执行生产部署脚本，以隔离命令替身代替 git/pip/systemctl/flock/timeout（不操作真实服务）：安装→停服→备份→启动顺序；停服失败/假成功、备份失败、健康检查失败不会误报成功；部署冲突、路径不匹配、本地脏修改、安装失败不停止旧服务；首次安装可完成。
- Bash 语法检查通过。命令替身验证编排和失败分支，不代替远程 Linux systemd 或云盘性能验收。

最终结果：20 项测试全部通过（30.60s），Git Bash 语法和 git diff --check 通过。实际命令行对停服备份副本执行分块复制及 integrity_check 成功，正确输出各阶段和最终 DB_BACKUP。

本地服务已于 2026-10-17 19:05:23 备份并重启，备份 runtime/before_deploy_optimization_20261017_190523/player.sqlite3，日志 runtime/deploy_optimization_20261017_190523.err.log，端口 ready 且 connectInfo 返回 local。活跃存档未覆盖，远程未部署。
