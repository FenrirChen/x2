# 数据库长期持锁排查及修复（2026-10-17）

## 线上证据与结论边界

用户提供的日志显示，旧 PID 1193492 一直运行（NRestarts=0），但 17:50～17:54 多次在 SaveManagerAPI._auth → AccountStore.verify → SELECT accounts 报 sqlite3.OperationalError: database is locked；服务重启为 PID 1256809 后，18:05 的账号初始化、邮件、好友及物品请求恢复。

fuser 当时只显示游戏服务占用正式数据库，无外部占用进程证据。此前部署备份进程的 D 状态、pread64 内核栈和累计读写量反映磁盘等待，不能直接证明数据库损坏，也不能把其累计读取量当成文件体积。

代码可确定的缺陷：经济事务、家园事务、兽主预设事务和友情点修复均只捕获业务执行异常，将 RELEASE 放在异常保护之外。最外层 RELEASE 相当于提交；提交遇到 SQLITE_BUSY 时，SQLite 保持事务及锁有效。失败后下一次 SAVEPOINT 会成为旧事务的内层，成功 RELEASE 也不会结束旧事务，因此能够长期阻塞其它连接。原账号验证语句是被阻塞者，日志不足以确定最初是哪个业务操作触发。

## 可重现证据

临时数据库，使用生产现有 DELETE journal 模式，不访问活跃存档：

1. 第二连接 BEGIN DEFERRED 并 SELECT，保持读事务（模拟并发完整存档导出）。
2. EconomyService.transaction UPDATE 后最外层 RELEASE 超时。
3. 原代码输出：COMMIT_ERROR: database is locked；TRANSACTION_LEAKED: True。
4. 独立 AccountStore.verify 的 SELECT 同样失败：AUTH_READ_ERROR: database is locked。
5. 释放读连接，再成功执行一次经济事务，原连接仍 in_transaction=True。需显式 rollback 或关闭连接才结束。

这是与线上现象一致的确定性代码缺陷，不声称已经从现有日志还原线上首次冲突的完整时序。

## 修复

新增 player/transactions.py 并供上述四处共用：

- 把业务体和 RELEASE 都纳入异常保护。当前作用域拥有最外层事务时，异常执行完整 rollback，解除锁。
- 已存在外层事务时，只回滚到当前作用域并释放保存点，不提交、不丢弃调用者已有工作。
- SQLite 已自动回滚（如 INSERT OR ROLLBACK）的情况不再发出无效保存点操作，不掩盖原异常。
- 数据库异常日志包含 stage、nested、耗时、sqlite_errorname，便于今后区分业务阶段和提交阶段，不打印账号密码、令牌或 SQL 参数。
- 失败请求保持失败，不补发成功，不重试可能重复发奖的业务操作。

不切换 WAL 模式、不改变同步持久化策略、不扩大等待超时、不改数据库/备份格式。

## 其它检查

- SaveManager.export_save 和 normalized_state 使用一致性读事务；export 的序列化/ZIP 压缩已经位于 COMMIT 之后。大型存档或慢磁盘会扩大读写竞争窗口；不能为缩短锁而删减导出数据。
- SaveManager.import_save 的 COMMIT 已在 try 范围内，有 ROLLBACK 清理；本次没有发现相同的提交失败泄漏。
- AccountStore 写入使用连接上下文或显式回滚，不是本次复现的泄漏位置。
- 扫描 player 下 with transaction 的 AST，未发现作用域内包含 await 的情况。
- deploy/deploy_server.sh 的全库备份和 integrity_check 无进度及超时，且停服前进行，解释了部署期间可能长时间无输出；这是部署可观测性/耗时问题，本轮未更改。

参考 SQLite 官方说明：
https://www.sqlite.org/lang_transaction.html（2.3：COMMIT 返回 BUSY 时事务仍有效）
https://www.sqlite.org/lang_savepoint.html（最外层 RELEASE 等同 COMMIT）

## 验证

专项测试 11 项通过：四处真实锁冲突、登录在读事务仍存在时恢复、后续写入落盘、嵌套事务整体回滚、内层失败保留外层修改、友情点不提前提交、SQLite 自动回滚、提交时延迟外键失败。

完整相关回归：103 passed in 104.33s，覆盖经济系统、家园状态与原子交换、兽主预设、账号存储、完整存档导入导出及 HTTP 接口、社交每日刷新。git diff --check 通过。

本地服务于 2026-10-17 18:12:12 重启；活跃存档未覆盖，先备份至 runtime/before_lock_recovery_20261017_181212/player.sqlite3。启动日志 runtime/lock_recovery_20261017_181212.err.log，三个端口 ready，HTTP connectInfo 返回 local。远程服务未由本轮操作更改。
