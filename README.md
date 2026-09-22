# X2 Revive Server

这是面向《解神者：X2》简体中文 Android 2.4 客户端的数字保存与协议兼容研究工程。项目目标是在不依赖原运营服务的前提下，逐步建立可验证、可维护的兼容后端。

本项目**不是**完整复活版、官方服务器、破解工具或在线服务。目前已完成工作区、协议核心和 TCP 连接层，并静态恢复了最小 bootstrap 合同；尚未完成原客户端 First Contact、登录处理、玩家数据库或游戏业务。

## 来源客户端

- Package：`com.siva.project.x2`
- Version：2.4（versionCode 202）
- APK SHA-256：`26a47aa684576549142cf0e4d096a78b90446314506626d2f9e57e6f76450bbe`
- Runtime：Unity 2017.4.39f1 / IL2CPP

## 当前状态

- M0 Workspace：Done
- M1 Protocol Core：Done
- M2 TCP Connection：Done
- M3 WebGameConfig Bootstrap：Partial（最小静态合同已恢复，原客户端尚未验证）
- FC First Contact：Not Started（本地安全路由/TLS 尚未闭环）
- M4 及以后：Not Started

协议实现覆盖 PackInt、protobuf wire 基础、请求/响应头、CRC32、packet framing、增量流解析、消息注册及离线 synthetic fixture。证据强度使用 `CONFIRMED`、`INFERRED`、`TEMPORARY_COMPAT` 明确区分。

## 运行测试

```powershell
python -m pytest
```

若使用隔离环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest
```

Packet inspector 只读取本地文件：

```powershell
python tools\packet_inspector.py tests\fixtures\synthetic_guide_request.bin --direction request
```

## 目录

- `src/x2server/protocol/`：协议编码、framing、schema 与 registry。
- `src/x2server/network/`：TCP listener、连接生命周期、dispatcher 与会话状态。
- `src/x2server/bootstrap/`：synthetic 回归模型和静态恢复的两段 bootstrap 合同。
- `src/x2server/config/`：非秘密配置。
- `tests/`：离线、确定性测试和 synthetic fixtures。
- `tools/`：本地协议检查工具。
- `docs/`：架构、里程碑、ADR 与证据来源。
- `reverse_data/`：仓库外逆向成果的索引，不复制大型文件。
- `runtime/`：未来运行时数据；除 `.gitkeep` 外不提交。

## 修改原则

先更新证据与 `docs/protocol_spec.md`，再更新测试，最后修改实现。不要把 `INFERRED` 或 `TEMPORARY_COMPAT` 写成原始客户端的已确认行为。提交应范围单一、测试通过，不得加入 APK、凭据、私钥或运行日志。

## 已知限制

当前没有真实官方抓包。fixture 均由已恢复协议规范或静态客户端证据在本地构造。尚未验证真实客户端互操作，也未实现 Login 业务、战斗签名语义或持久化。TCP listener 默认只监听 localhost；bootstrap 字段与路径已恢复，但有效 `GameConfig.txt` 基址及本地安全导流仍为 UNKNOWN。
