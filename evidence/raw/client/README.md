# Raw Client Evidence（实际位置索引）

| Evidence ID | 实际路径 | 说明 |
|---|---|---|
| CLIENT_APK_REFERENCE_2_4 | `D:/demo/x2/X2_Eclipse_v2_4.apk` | Reference APK，永久原样 |
| CLIENT_IL2CPP_2_4 | `D:/demo/x2/phase3_work/lib/arm64-v8a/libil2cpp.so` | ARM64 原生代码 |
| CLIENT_METADATA_2_4 | `D:/demo/x2/phase3_work/assets/bin/Data/Managed/Metadata/global-metadata.dat` | IL2CPP metadata |
| CLIENT_DUMP_CS | `D:/demo/x2/tools/Il2CppDumper-bin/dump.cs`（含 script.json/stringliteral.json） | 类/字段/RVA dump |
| CLIENT_UNITYSERIALIZED_2_4 | `D:/demo/x2/phase2_output/` | 1,526 bundle + 7,934 SerializedFile 清单 |
| CLIENT_RAW_TABLES_2_4 | `D:/demo/x2/phase3_output/raw_tables/` | 70 个解密表 blob（多版本） |

运行时观测 trace 在 `evidence/raw/runtime_traces/`。
以上路径不搬动：多个 xref/解析工具以这些绝对位置为准。
