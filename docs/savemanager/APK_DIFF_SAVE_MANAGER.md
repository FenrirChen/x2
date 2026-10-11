# APK_DIFF_SAVE_MANAGER.md — SaveManager APK 相对 AllocatorFix 基线差异

- 基线: `逆向/打包/X2-Revival-AllocatorFix-signed.apk`，2,145,044,177 bytes
- 最终: `tools/savemanager/client/build/X2-Revival-SaveManager-signed.apk`（同副本交付于 `逆向/打包/X2-Revival-SaveManager-signed.apk`），2,144,999,251 bytes
- 距 2³¹−1 裕量: **2,484,396 bytes**（硬约束 < 2,147,483,647 ✅）
- 条目数: 12644 → 12646（新增 2；重签重建 3 个 v1 签名条目；v2/v3 块由 sign_release.ps1 重写）

## 1. 新增条目

| 条目 | 压缩大小 | 说明 |
|---|---|---|
| `classes5.dex` | 8,885 | SaveManagerBridge + SaveManagerDialogFragment（javac+d8） |
| `lib/arm64-v8a/libx2save.so` | 6,795 | 存档管理桥（C，zig cc 编译，DT_NEEDED libc.so/libdl.so） |

## 2. 内容变更条目（游戏数据；均为原位等长替换或 hook）

| 条目 | 基线 CRC | 最终 CRC | 变更 |
|---|---|---|---|
| `assets/bin/Data/844762d28a77f85408b631eb3f0186bc` | `3363072D` | `AB07099D` | 游客登录→存档管理 / 遊客登入→存檔管理（原位等长 UTF-8 替换，解压后同长度） |
| `assets/bin/Data/9f7c8bf97310515489bb8c18404a80bf` | `DF257AF6` | `28A6EBD5` | 游客登录→存档管理 / 遊客登入→存檔管理（原位等长 UTF-8 替换，解压后同长度） |
| `assets/bin/Data/bf39f9c839b67204eadd3371ec9025c9` | `C0FF9E15` | `542D87B5` | 游客登录→存档管理 / 遊客登入→存檔管理（原位等长 UTF-8 替换，解压后同长度） |
| `lib/arm64-v8a/libil2cpp.so` | `58227887` | `66905B63` | 1 指令 hook（0x15166F0）+ code cave trampoline（0x42B02C0） |
| `res/layout/dialog_dhui2_login.xml` | `F1F4D5AF` | `3A1A1CF3` | 游客登录→存档管理 / 遊客登入→存檔管理（原位等长 UTF-8 替换，解压后同长度） |

### 重签产物（apksigner v1 重新生成，非内容变更）

- `META-INF/MANIFEST.MF` CRC 1E3C205C → 36323F93
- `META-INF/X2-REVIV.RSA` CRC 039380E7 → D992520E
- `META-INF/X2-REVIV.SF` CRC 615E956E → 845ED34E

## 3. 逐字节一致的关键条目

| 条目 | 判定 |
|---|---|
| `lib/arm64-v8a/libunity.so` | ✅ SHA256 `7c5a3c1f457572727020d498bc894a0832cc1dcd415d1a35a3c59e0ee10c8aa5`（allocator 修复零回归） |
| `AndroidManifest.xml` | ✅ 未修改（versionCode 202 / versionName 2.4 不变；已确认 versionCode 不参与 bootstrap/协议检查，保守不递增） |
| `assets/42c44a368fc3544296d1e717a485b306.ab`（加密 GameConfig） | ✅ 未修改 |
| 其余 12,636 条 | ✅ 逐字节一致 |

## 4. 新增净体积

- 新增条目压缩计: **15,680 bytes**（建议 <1 MB ✅；无第三方大库/图片/字体/Web 框架/Gum）

## 5. 签名

- apksigner v1+v2+v3 全部 Verified；证书 SHA256 `c30b8137…3642c28` 与发布身份一致。
- 最终 APK SHA256: `d436f79e11e05fa8b72b9f2096e121be4c1c43fc5c41847f492f5bf09a98da8b`