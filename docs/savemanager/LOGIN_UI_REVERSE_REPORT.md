# LOGIN_UI_REVERSE_REPORT.md — 登录界面"游客登录"按钮逆向报告

任务：存档管理客户端改造的第一步（任务第二十~二十二节）。全部结论来自静态逆向
（Il2CppDumper dump.cs + capstone 反汇编 + APK 资源字节级定位），**未凭截图猜测**。

## 1. 按钮定位

| 项 | 结论 |
|---|---|
| 所在 Scene/Prefab | `assets/bin/Data/9f7c8bf97310515489bb8c18404a80bf`（LoginPage MonoBehaviour 序列化数据，含 `UnityEngine, Version=1.0.0.0` 程序集引用与按钮默认文字串） |
| IL2CPP class | `LoginPage : UIBase`（dump.cs TypeDefIndex 11859，行 642130） |
| 字段 | `mTxtPassword` (InputField) @0x88、`mTxtAccount` (InputField) @0x90、`mBtnVisitorLogin` (Button) @0xA8 |
| Click handler | `LoginPage.OnMBtnVisitorLoginClick` @ libil2cpp.so (arm64) RVA `0x15166F0` |
| 原行为 | 校验后取 `LoginManager` 单例（0x1ADA664）→ 尾调 `LoginManager.OnVisitorLogin()` @ `0x1AEB794`（`new Random().Next()%10000` 生成 `user{0}` 访客名 + 空密码走 `/loginwithpw`） |
| 账号输入框内容读取 | `mTxtAccount.get_text`（InputField.text，IL2CPP 属性；prefab 与 dump.cs 双重确认） |
| 密码输入框内容读取 | `mTxtPassword.get_text` |

证据：`analysis/account_registration/current_auth_flow.md`（Phase 13/14 实机链路 +
本轮 0x15166F0/0x1AEB794 反汇编复核：`mov x19,x0` 保存 this、`bl 0x1516788` 校验、
尾部 `b 0x1AEB794` 尾调，均与本报告一致）。

## 2. 按钮文字来源

"游客登录" 以 UTF-8 明文出现在基线 APK 的 4 个条目（全量扫描，其余 12,639 条目无命中）：

| 条目 | 性质 | 命中 |
|---|---|---|
| `assets/bin/Data/bf39f9c839b67204eadd3371ec9025c9` | protobuf 语言表（语言 ID 246：zh-CN"游客登录"/zh-TW"遊客登入"/ko/ja） | 1 zh-CN + 1 zh-TW |
| `assets/bin/Data/844762d28a77f85408b631eb3f0186bc` | 语言表（同结构，另一版本，大 ID） | 2 zh-CN + 2 zh-TW |
| `assets/bin/Data/9f7c8bf97310515489bb8c18404a80bf` | LoginPage prefab 序列化字符串（长度前缀 0x0C=12 字节） | 1 |
| `res/layout/dialog_dhui2_login.xml` | 网易 DHUI SDK 登录对话框布局（Account 模式不使用） | 1 |

判定：类型为 **prefab/UI Text 序列化字符串 + 语言表条目**（非 TMP/sprite/runtime 赋值）。

## 3. 文字修改（第二十一节优先级 2：最小修改 text）

- 替换对：`游客登录 → 存档管理`、`遊客登入 → 存檔管理`（均为 12 UTF-8 字节，**原位等长替换**，零长度变化，容器结构/偏移/字段不受影响）。
- 不修改 ko/ja 条目（等长约束不满足；简中客户端不受影响，报告中声明）。
- 按钮背景/位置/动画/尺寸/美术风格全部保留（未触碰任何 Image/RectTransform/DOTween 数据）。
- 工具链证明：构建日志 8 处替换 + 校验器全 APK 扫描 0 残留（见 APK_DIFF_SAVE_MANAGER.md）。

## 4. 行为修改（第二十二节：新 Save Manager）

入口 hook（libil2cpp.so，arm64，RVA 即文件偏移，第一 LOAD 段 vaddr==offset）：

```
0x15166F0  stp x20,x19,[sp,#-0x20]!   →   b 0x42B02C0    （跳入 code cave）
```

cave（0x42B02C0，基线全零区，无重定位指向；3684 字节空间仅用 ~330 字节）：

```
stp x20,x19,[sp,#-0x20]!          ; 被替换指令原样执行
stp x29,x30,[sp,#0x10]
mov x19, x0                       ; this = LoginPage
adrp/add x0, "libx2save.so"       ; cave 内字符串
mov w1, #1                        ; RTLD_LAZY
bl  dlopen@PLT (0x113E820)        ; libil2cpp 自带 dlopen 导入
cbz x0, fallback
mov x20, x0
adrp/add x0, "x2_open_save_manager"
mov x1, x20
bl  dlsym@PLT (0x113FA80)
mov x1, x20                       ; arg2 = libil2cpp 句柄
mov x2, x0
mov x0, x19                       ; arg1 = LoginPage*
cbz x2, fallback
blr x2                            ; w0 = 1(已处理)/0(失败)
cbnz x0, handled
fallback: mov x0, x19 ; b 0x15166F8   ; 桥缺失时回落原游客登录行为
handled:  ldp x29,x30,[sp,#0x10] ; ldp x20,x19,[sp],#0x20 ; ret
```

- **不执行原游客登录**（桥加载成功时）；桥加载失败才回落（库随 APK 分发，正常不存在）。
- 账号/密码**复用现有输入框**（通过 il2cpp C API 读 `mTxtAccount/mTxtPassword` 的
  `get_text`），无需用户重新填写；为空时由 Java 侧提示"请输入账号和密码"。
- 桥同时读取 `GameConst.Login_Url`（public static string @0xD0，dump.cs 行 500409，
  即 Revival 补丁后的服务器地址）传给存档管理界面 → **不硬编码新 IP**（第二十六节）。

## 5. 安全村（cave）安全性证据

| 检查 | 结果 |
|---|---|
| 基线 cave 全零（0x42B02C0..+512） | ✅ |
| .rela.dyn/.rela.plt 无重定位指向 cave | ✅ |
| 汇编后经 capstone 独立反汇编逐指令核对（含 PC 相对目标） | ✅（tools/savemanager/client/patch_il2cpp.py 内建验证） |
| libunity.so 未修改（SHA256 7c5a3c1f… 保持） | ✅ |
