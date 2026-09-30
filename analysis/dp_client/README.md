# 客户端 DP 数据核对（2026-09-30）

来源：原始 `D:\demo\x2\X2_Eclipse_v2_4.apk`，ResourceManager 的正式 table 引用。
流程：TextAsset -> Resources.ConvertDataBytes（RSA 首块及双向幂次位置 XOR）-> 完整数组 protobuf。
七张表均完整解码、行主键与 Keys 一致、消费全部字节，**没有修补任何所谓坏字节**。
`manifest.json`记录外部资源名和原始载荷SHA256；`used_rows.json`保留本功能引用的条件、Item及Gift原始字段。

## 核对结果

- ChapterInfo：13行；TaskChapter：260行；TaskCondition：1728行；TaskConditionLine：139行。
- 宝箱门槛：实际20/40/60/80/100点，无百分比换算。
- 第1–9、11章任务总点数均100；第10、12章仅一条2点占位任务，未补造。
- 多档目标和多档DP奖励逐项累加。例如650101：击败3031/3622/3628累计150、250、500次，分别增加1、1、2点。
- CompleteValue1/2是完整条件ID集合，不能只取首个。精确五星条件[5]不含六星；五星及以上条件明确列出[5,6]。
- 651113条件600091完整恢复：击败异化黑羊5040一次，2点。
- 50个唯一宝箱均可从Item.Used连接Gift确定实际奖励。1203846–50缺文本但不缺Gift。
- 1203841描述写“卡恩斯x10/魂石源质x5”，Gift730950明确发卡恩斯碎片1201013x10、魂石源质1251090x10、金币1237901x20000。
- 宝箱第二档六件兽主的部件ID取自GiftValue，四星取自GiftShow对应Item语言名称“4★套装”，没有按描述猜造。
- TaskData.stage使用当前目标档的零基索引；达到最后一档后为完成状态，累积进度不重置。客户端GetClientDpNum（RVA0x1AD850C）遍历CompleteNum/DPPoint累加；GetServerAchievementData（0x1AD632C）读取TaskData.stage（偏移0x24）。

## 图片交叉核对

已查看 `D:\demo\x2\other\pic` 的全部七张图：

| 文件 | 章节 |
| --- | --- |
| b5c2e2e792e69a4d3f3d1165dbc10b08.jpg | 1 |
| fef1e06935c476b046f78e57b77d0e1f.jpg | 2 |
| 0fe348855a2d153241346981a144a205.jpg | 3 |
| ce82ed10cb2ae6f46ae9337e62c090b9.jpg | 4 |
| b1427e12a53783f9b559979f80f986d0.jpg | 5 |
| cf65896d17f110036ccc10c0d8c9ee21.jpg | 6 |
| c4705c72d6ff3e4362ec3c84523a6cd4.jpg | 7 |

图片只列部分首档目标，部分数值与2.4客户端不同。例如第二章海拉残像图为5次/+4，客户端为1次/+2、5次/+4两档；第二章Boss图为15次/+6，客户端为15次/+6；第一至七章图源质普遍x10，但2.4部分宝箱描述写x5，Gift实际x10。以客户端完整条件和执行Gift为准。
图片没有第10–12章补充资料，不用旧图补造占位任务。

## 重建

```
.venv\Scripts\python.exe tools\analysis\extract_dp_client_evidence.py
.venv\Scripts\python.exe tools\analysis\build_dp_client_catalog.py
```

提取依赖项目外层 `.phase2_deps` 中已有的UnityPy。大型原始载荷输出至忽略目录 `raw/`，仓库保留哈希和相关行证据。
正式DB没有批量修改，服务未重启，代码仅本地Git提交。
