# X2 Revive Server

这是面向《解神者：X2》简体中文 Android 2.4 客户端的数字保存与协议兼容研究工程。项目目标是在不依赖原运营服务的前提下，逐步建立可验证、可维护的兼容后端。

本项目**不是**完整复活版、官方服务器、破解工具或在线服务。目前只完成 M0 工作区和 M1 协议核心；没有 TCP 监听、WebGameConfig、登录处理、玩家数据库或游戏业务。

## 来源客户端

- Package：`com.siva.project.x2`
- Version：2.4（versionCode 202）
- APK SHA-256：`26a47aa684576549142cf0e4d096a78b90446314506626d2f9e57e6f76450bbe`
- Runtime：Unity 2017.4.39f1 / IL2CPP

## 当前状态

- M0 Workspace：Done
- M1 Protocol Core：Done
- M2 TCP Connection：Done
- M3 WebGameConfig Bootstrap：Partial（HTTP 基础完成，官方 body/path 仍未知）
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
- `src/x2server/network/`：连接状态薄抽象；M1 不创建 socket。
- `src/x2server/config/`：非秘密配置。
- `tests/`：离线、确定性测试和 synthetic fixtures。
- `tools/`：本地协议检查工具。
- `docs/`：架构、里程碑、ADR 与证据来源。
- `reverse_data/`：仓库外逆向成果的索引，不复制大型文件。
- `runtime/`：未来运行时数据；除 `.gitkeep` 外不提交。

## 修改原则

先更新证据与 `docs/protocol_spec.md`，再更新测试，最后修改实现。不要把 `INFERRED` 或 `TEMPORARY_COMPAT` 写成原始客户端的已确认行为。提交应范围单一、测试通过，不得加入 APK、凭据、私钥或运行日志。

## 已知限制

当前没有真实官方抓包。fixture 均由已恢复协议规范本地生成。尚未验证真实客户端互操作，也未实现 Login 业务、战斗签名语义或持久化。TCP listener 已具备，但默认只监听 localhost；bootstrap 的官方响应字段与准确路径仍为 UNKNOWN。
