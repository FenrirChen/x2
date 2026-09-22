# X2 Revive Server


这是面向《解神者：X2》简体中文 Android 2.4 客户端的数字保存与协议兼容研究工程。项目目标是在不依赖原运营服务的前提下，逐步建立可验证、可维护的兼容后端。

本项目已完成协议核心、TCP 连接层、最小 Bootstrap、稳定实验入口启动和 Revival v0.2。Phase 13 已两次解析真实客户端 C2L_Login（54），CRC/protobuf 校验通过，并核实本地身份 token；尚未实现 L2C_Login、玩家数据库或游戏业务。

最新实验与进度以 [Phase 13 报告](docs/phase13_first_contact.md) 为准。根目录早期 README、Phase 10 与早期导流文档包含历史状态，不应据此重做已完成工作。

## 来源客户端

- Package：`com.siva.project.x2`
- Version：2.4（versionCode 202）
- APK SHA-256：`26a47aa684576549142cf0e4d096a78b90446314506626d2f9e57e6f76450bbe`
- Runtime：Unity 2017.4.39f1 / IL2CPP

## 当前状态

- M0 Workspace：Done
- M1 Protocol Core：Done
- M2 TCP Connection：Done
- M3 WebGameConfig Bootstrap：Partial（controlInfo/connectInfo 已验证；Account 路径经 httpLogin 返回 TCP 地址，address 未实机验证）
- Revival v0.2：已构建、沿用原开发签名覆盖安装；Reference APK 保持原样。
- Startup：Phase 12 实验入口验收通过，三次冷启动显示正常加载画面并到达 controlInfo。
- FC First Contact / M4 Login Decode：两次真实消息 54 解码通过，身份匹配；未发送业务回复。
- M5 及以后：Not Started

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

当前没有真实官方抓包。协议 fixture 均由已恢复协议规范或静态客户端证据在本地构造。Revival 客户端已请求本地 controlInfo，服务返回 HTTP 200，但 connectInfo/address 和 TCP 互操作尚未验证；未实现 Login、战斗签名语义或持久化。阶段一观察服务仅监听 localhost，使用 ADB 直接进入 Unity 的实验入口，尚不代表图标启动、渠道登录或完整游戏可玩。
