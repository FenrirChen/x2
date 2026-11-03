# 22702 成品资产（参考包 `X2-Revival.apk`）

这些是本 PR 工具在已实机复核的参考包 `X2-Revival.apk` 上生成的成品；
把同名 `.bin` 覆盖 APK 的 `assets/bin/Data/<原条目名>` 后重签即可打包。

**基包必须与生成时一致（下表的输入 SHA-256）。** 如果基包已经叠加了其它会改
`globalgamemanagers` / `DrawRules` / `Gift` 的补丁，整文件替换会覆盖那些补丁；
这种情况下请用 `python tools/patch_jewel_pool_702.py --apk <你的基包> --output <目录>`
对基包重跑，不要直接覆盖。

| zip 条目 | 成品文件 | 字节 | SHA-256 |
| --- | --- | --- | --- |
| `11f10428ab85c83458e81c7c4acc3909` | `11f10428ab85c83458e81c7c4acc3909.bin` | 2819504 | `43bd88dfc561c9eb3ff0d2b47322a84eee50bd0e6b929c9e9bd579b3ce8258ed` |
| `2f27eb218a7d46144b76f8574a7912ca` | `2f27eb218a7d46144b76f8574a7912ca.bin` | 4165496 | `36795e27ac28abcbcb5906d11b0fb15177ee758f5aa1c88105a04350ca6c69cf` |
| `83629c106e3c12644a26a22b89a7f24d` | `83629c106e3c12644a26a22b89a7f24d.bin` | 1136840 | `058d5ee219bbe2de7627ea9ee6ebb51d7a997c037c886b001dcdb8765a194e47` |
| `globalgamemanagers` | `globalgamemanagers.bin` | 21864280 | `33777f3b22a45e646011943a3a0350a1abc4bcd436f2eab8ad98eb8d4f0f0f3e` |
| `794cf065a19ef3543aa8ec8dda10e252` | `794cf065a19ef3543aa8ec8dda10e252.bin` | 11864 | `417027ed7c32a3d1d1e5774940a96c040fc6da027947fd204639a60fc3791498` |
| `109c23e5b633a7943b46f54df86ab23e` | `109c23e5b633a7943b46f54df86ab23e.bin` | 12128 | `2e1a8e86cab67a703c6f5fb843864353b158f2300cc020f5c86e13b3cc3d0f75` |
| `97f907f95af754641b60175964616b99` | `97f907f95af754641b60175964616b99.bin` | 355968 | `baf39d2ea80c6425d14dabd4fe87d3e9db1fd1766f9379d891fcf1c7217dae7c` |

## 来源

- 输入参考包：`X2-Revival.apk`（本 PR 记录 7 个输入条目 SHA-256；见 compatibility 文档）。
- 生成命令：`python tools/patch_jewel_pool_702.py --apk <reference.apk> --output <目录>`。
- `audit.json` 是工具的自检明细；`manifest.json` 是条目 -> 成品文件名映射。
- 三张源图仍保留在 `tools/assets/jewel_pool_702/`，替换素材后可用工具重新生成。
