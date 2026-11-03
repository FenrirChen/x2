# 客户端存档导入开关

X2_SAVE_IMPORT_ENABLED默认0，关闭玩家HTTP存档导入。设为1恢复导入；同时接受true、yes、on，不认识的值按关闭处理。部署后默认关闭，无需改APK；现有进程须重启以读取系统环境配置。

远程常规配置文件为/etc/x2server/x2server.env：设置X2_SAVE_IMPORT_ENABLED=0关闭，设为1开启，随后systemctl restart x2server.service。本轮只修改本地代码，不操作远程。

关闭返回HTTP503、save_import_disabled及中文提示，在API取得共享任务槽之前拒绝，不解析ZIP、不做备份、不启动导入工作进程、不改玩家存档、不吊销现有令牌。认证、状态查询和导出保持可用。该开关控制玩家客户端接口，离线管理员直接调用SaveManager的恢复能力保留；不会中断关闭前已经开始的导入。HTTP层仍会接收受大小限制的上传体，不代表停止上传流量。
