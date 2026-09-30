# 官方 2.4「终端」名称对应表

证据来源：`D:/demo/x2/X2_Eclipse_v2_4.apk` 解包的 `phase3_work/lib/arm64-v8a/libil2cpp.so`、`tools/Il2CppDumper-bin/dump.cs` / `script.json`，以及同版静态表 `analysis/drop_archaeology/full_tables/`。RVA 均为 arm64 `libil2cpp.so` 虚拟地址。未使用服务端 handler 名称推断客户端系统。

| 显示/代码名称 | 直接证据 | 定位结论 |
|---|---|---|
| 终端 | `LanguageUI.Key=261`；`Language.Key=210033` 为「点击这里进入【终端】界面」 | 大厅显示名。语言键没有独立的模块语义。 |
| 开始分析 | `LanguageUI.Key=4908`，相邻键 4909 为英文 `START THE ANALYSIS` | 终端内分析按钮文案。 |
| `mBtnPrivateLetter` | `MainPage` 字段偏移 `0x170`，`OnMBtnPrivateLetterClick @ 0x13D19B8` | 大厅入口的客户端字段/处理方法。官方 prefab 未在当前 APK 静态资源集中找到，无法直接展示 Key 261 到该 Button 的序列化绑定；此处由用户提供的按钮位置/文案与入口调用链交叉定位。 |
| `PrivateMailModule` | 大厅 click 的泛型方法元数据地址 `0x52D7958 -> Method$Foundation.Module.ModuleManager.ShowModule<PrivateMailModule>()` | 「终端」的**内部入口模块**，不是普通游戏聊天、占卜或系统邮件。 |
| `FavorCommunityMain` / `UI_PrivateMail` | `PrivateMailModule.Show @ 0x15CB00C` 调用 `UIManager.OpenUI<FavorCommunityMain>`，方法元数据 `0x51FC508`；UI 路径字符串 `UI_PrivateMail` | 终端主面板。`FavorCommunityMain.OnInit @ 0x1AA1EE0` 注册三个 Tab：`FavorWishTab`、`FavorPrivateLetterPage`、`FavorMomentsTab`。 |
| `FavorWishTab` | `mBtnAnalyse` 字段偏移 `0x38`，`StartPage`/`ChoosePage`/`TaskPage` 三个页面字段；`OnMBtnAnalyseClick @ 0x18BC3EC` | 「开始分析」属于终端中的**神格心愿任务 Tab**。Key 4908 到 Button 的 prefab 序列化引用同样缺失；按钮字段/方法和界面文案相互印证。 |
| `FavorWishModule` | `FavorWishTab.OnMBtnAnalyseClick` 原生尾调用 `FavorWishModule.AskServerData @ 0x18B9A70` | 分析按钮的业务模块。 |
| `FAVORDAILY` | 官方 `GameTaskType.FAVORDAILY=6`；`FavorWishModule.AskServerData` 向 `MainModule.SendGameTask` 传入 `type=6` | 主请求是心愿任务分析/生成查询。 |

`LanguageUI` 的 4891–4909 区段同时含 CONNECT、私信、系统消息、动态、任务信息和「开始分析」。这只是文案上下文；系统判定依靠上面的 native 调用链。

**前次「终端 = 心愿任务」判断：CONFIRMED（限定「开始分析」子流程）。** 整个终端容器的内部入口是 `PrivateMailModule` / `UI_PrivateMail`，还包含私信和动态；不能把整个容器缩成单一任务系统。
