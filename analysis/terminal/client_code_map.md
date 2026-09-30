# 客户端代码与调用链

版本和地址来源见 `aliases.md`。`dump.cs` 的泛型共享入口常显示错误的实例化类型；下表涉及泛型时，已用 `libil2cpp.so` 中调用点装入的 Method 元数据指针，与 `script.json.ScriptMetadataMethod` 交叉核对。例如反汇编把 `0x13D1A50` 注成 `ShowModule<MoonNPCFavorabilityModule>`，但调用点 `0x52D7958` 的真实实例是 `ShowModule<PrivateMailModule>`。

| 顺序 | Class.Method / RVA | 原生代码证据与作用 |
|---|---|---|
| 1 | `MainPage.mBtnPrivateLetter` (`+0x170`); `MainPage.OnMBtnPrivateLetterClick @ 0x13D19B8` | 点击上报 button 8；`0x13D1A50` 调用 `ShowModule<PrivateMailModule>`，元数据 `0x52D7958 -> 0x5527778`。`_MBtnPrivateLetterClick @ 0x13D1A54` 跳向同一方法。 |
| 2 | `PrivateMailModule.Show @ 0x15CB00C` | 检查功能开放；将 `UI_PrivateMail` 作为跳转页面，调用 `UIManager.OpenUI<FavorCommunityMain>`；泛型元数据 `0x51FC508 -> 0x5531638`，字符串元数据 `0x52E1A60 -> UI_PrivateMail`。 |
| 3 | `FavorCommunityMain.OnInit @ 0x1AA1EE0` | 三个 Tab 泛型元数据：`0x525ED70=FavorWishTab`、`0x52F8CC0=FavorPrivateLetterPage`、`0x5291BE0=FavorMomentsTab`。 |
| 4 | `FavorWishTab.Init @ 0x18BA768`; `OnOpen @ 0x18BB52C`; `OnMBtnAnalyseClick @ 0x18BC3EC` | 字段 `StartPage(+0x30)`、`mBtnAnalyse(+0x38)`、`ChoosePage(+0x40)`、`TaskPage(+0x58)`。OnOpen 先用 `AskServerData(false,false)` 查询；分析按钮调用 `AskServerData(false,true)`。 |
| 5 | `FavorWishModule.AskServerData @ 0x18B9A70` | `w19 ← w2(isAnalyze)`，尾调用前置 `w1=6`、`w2=w19 & 1`、`w3=0`，因此 `MainModule.SendGameTask(type=6, extraType=isAnalyze, chapterId=0)`。按钮参数实际为 `6,1,0`；`isRefresh` 入参未在此发送路径使用。 |
| 6 | `MainModule.SendGameTask @ 0x13C4508` | 将参数写入缓存的 `C2L_GameTask.type(+0x10)`、`extraType(+0x14)`、`chapterId(+0x18)`，经 `MarsNetManager.Send<C2L_GameTask>` 发送；请求 ID `351`。官方 `QueryExtraType.GENMIND=1` 正是分析/生成请求的标志。 |
| 7 | `MainModule.OnReceiveGameTaskMsg @ 0x13C135C` | 消费 `L2C_GameTask` ID `354`；`code=10` 成功进入按 `type` 分发，`type=6` 的跳表目标 `0x13C1AC8` 通往事件 223；`code=173 (E_NOT_GEN_MIND_TASK)` 且 `type=6` 也触发事件 223。其他错误走错误提示。 |
| 8 | `FavorWishModule.InitData @ 0x18B92D8`; `OnReceiveFavorWishMsg @ 0x18B9B6C` | 注册 `GAMETASK_RECEIVE_FAVORDAILY=223` 事件消费 `L2C_GameTask`；清空并填充任务列表、排序，触发 UI 刷新事件 `UI_GAMETASK_REFRESH=218`，刷新 badge。 |
| 9 | `FavorWishTab.CalPageState @ 0x18BB6B4`; `RefreshFavorWish @ 0x18BB5F8` | 根据返回任务列表、选择/接受状态切换 `StartPage`、`ChoosePage`、`TaskPage`。列表为空会回到 StartPage，视觉上等同「点击没反应」。 |
| 10 | `FavorWishTab.OnMBtnConfirmClick @ 0x18BC410`; `FavorWishModule.SendAcceptFavorWish @ 0x18BA0E8` | 候选任务选择后，发送 `C2L_AcceptFavorTask` ID `459`，字段 `taskIds` 和 `type=6`。 |
| 11 | `FavorWishModule.OnReceiveAcceptFavorWishMsg @ 0x18BA1CC` | 消费 `L2C_AcceptFavorTask` ID `460`；`code=10` 时设置 `isAnalyse=true`、发事件 218 并再查 `C2L_GameTask(type=6, extraType=0, chapterId=0)`；失败显示错误。 |
| 12 | `FavorWishModule.OnFinishFavorWishMsg @ 0x18B9F7C` | 后续任务领取/完成回调只在 `type=6` 分支更新状态，再发 UI 刷新事件。任务执行还依赖通用 `C2L_FinishGameTask` 路径。 |

## 证据边界

- `dump.cs` 只给类、字段、方法和 RVA；上面关键传参、跳表与事件分发来自 arm64 原生代码反汇编。`GameTaskType.FAVORDAILY=6`、`QueryExtraType.NULL=0`、`GameLogicErrCode.E_Ok=10`、`E_NOT_GEN_MIND_TASK=173` 在同版 `dump.cs` 枚举中明确声明。
- APK 中未找到 `UI_PrivateMail` 的可解析 prefab，因此无法以序列化对象直接证明 `LanguageUI.Key=261/4908` 写在具体 Button 上，也无法给出该 prefab 的 GUID/path ID。面板、按钮字段、方法和用户实际文案的对应已由代码路径交叉建立；这一项保留为资源证据缺口。
- 本轮没有把服务器日志中「没看到请求」当作客户端不发请求的证据。原生调用链明确显示按钮会走 MarsNet；实际点击是否受本地开放条件拦截仍需定点 telemetry 验证。
