# 活动换期后主界面持续连接：2026-10-11

第二期伪生樱之岛的实际日志显示，客户端发送请求1038后服务端记录 `unknown message ID; no response`。同一请求218在重连后反复重发，共32次。1038是 `C2L_SceneGlobalParam`，1039是 `L2C_SceneGlobalParam`，并非活动特有的新登录协议。

从客户端原生序列化恢复请求、响应及嵌套 `SceneSectionParam`，加入 `activity_wire.json`、注册表与活动运行时共用处理器。成功响应按 `SectionTable.Type` 分组返回当前期真实的关卡通过次数，不伪造已通关或解锁状态。客户端 `ActivityNoticeModule.OnReceiveSceneSectionParam` 保存列表，`CheckSceneSectionParam` 根据 ActivityDungeon 的前置关卡与次数判断解锁。所有实际列表均有条目；无关卡时使用零占位防止缺失列表。

同一登录链还触发活动商店数据编码异常：`ActivityShopGoods` 没有 `code` 字段，原实现误把普通商店外层应答整体作为嵌套内容。现去除外层 `code` 后编码嵌套商店，保留正常价格、库存、刷新时间和购买规则。

新增八个主题的正确初始化请求回归，断言1038注册及1039成功应答、初始次数0、真实通关次数4同步、正确活动类型的商店列表成功与嵌套协议解码。原先仅发送空参数的遍历检查无法发现有效商店请求中的字段污染；保留原遍历并增加有效请求检查。游戏内验收仍由用户完成。
