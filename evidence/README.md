# Evidence Layer

四层知识体系的第一层：证据。分三类，禁止互相混合。

- **raw/** — 官方 2.4 客户端直接产物 + 运行时观测。**DO NOT EDIT MANUALLY**。
  大文件（APK/libil2cpp.so/global-metadata.dat/解包目录）保留在原始位置，由
  `manifests/evidence_manifest.json` 登记真实路径与 SHA256，不复制、不搬动。
- **derived/** — 由脚本从 raw 可再生成的机器可读分析。canonical 路径登记在 manifest；
  每个产物必须能用 `tools/analysis/` 的生成器重跑。
- **external/** — 第三方资料（隔离，永不与 raw 混放）。`external/third_party/` 存放
  《解神者本地单服-数据对照表.xlsx》副本；`external/player_observations/` 存放玩家实测
  （如随机商店 22 条，见 external_crosscheck 报告）。

引用规范：文档里引用证据请用 Evidence ID（如 `CLIENT_IL2CPP_2_4`、`DROP_GRAPH`），
不要写"之前那个 json"。新增证据时运行 `tools/analysis/build_evidence_manifest.py` 重新登记。
