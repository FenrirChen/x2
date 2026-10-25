# 2026-10-25 用户指定日服美术补丁

## 来源与实施

用户指定目录：`C:/Users/18207/Downloads/反和谐/jp_bin`。目录只读，未修改原始资源或执行其中任何文件。README仅用作来源说明。

基线：上一轮完成赛季真实入口和静态背景修复的 `X2-Revival-ClientFix20261025-{Local,Remote}-signed.apk`。

10份资源均按原APK的 `assets/bin/Data/<哈希名>` 路径应用，8份替换、2份已完全相同。替换后的文件与用户原文件逐字节一致。不是只替换纹理：同时使用对应原始Sprite数据，避免沿用旧裁剪/网格造成新立绘被裁掉。

- 立绘：SkinDrawing_1221005、StarDrawing_1221902、StarDrawing_1221102、StarDrawing_1222702、Hero_F_drawing_1019。
- 角色卡：Hero_Icon_101902_H、Hero_Icon_101102_H、Hero_Icon_102702_H、Hero_Icon_101005_H。
- 模型纹理：texture_101001_1。
- 最后一个角色卡和模型纹理在基线中已包含相同原文件。

全部资源Unity版本为2017.4.39f1，原有文件名、对象PathID、类型、名称、纹理尺寸/格式和Sprite本地纹理引用匹配。无新增外部依赖；所有纹理与Sprite成功解码。未改变模型骨架、动画或服务器业务逻辑。

## 交付

目录：`D:/demo/x2/逆向/打包/`。

| 文件 | 地址 | SHA256 |
| --- | --- | --- |
| X2-Revival-ClientFix20261025-JP-Local-signed.apk | http://10.0.2.2:18080 | e50d1865f49c60fe5cd87f9be41cc995f74dd1a47a52eca900611be6d5d3aecc |
| X2-Revival-ClientFix20261025-JP-Remote-signed.apk | http://8.163.2.72:18080 | a803c8574b6cee2daf1d5635be67a7257435de876b932b83958882594340fcd6 |

每包2147166035字节，低于2GiB-1兼容性上限。沿用原发布证书，v1/v2/v3签名校验通过。

对比各自基线，除签名数据外仅8个指定Unity资源变化。全部10个目标文件SHA256与用户来源一致，其他ZIP条目未变；完整ZIP CRC、stored条目4字节对齐、原生库/Unity库/存档DEX及服务器地址均校验通过。因此上一轮赛季背景、实际章节标题、标题语音、六星鉴定、静影立绘和存档管理补丁保留。

模拟器覆盖安装尝试未执行成功：ADB设备列表为空，127.0.0.1:7555连接被拒绝。未把文件校验称为实机验收，旧包保留用于回退。

## 复用方式

工具：`tools/savemanager/client/patch_jp_artwork.py <现有APK> <jp_bin来源目录> <输出目录>`，生成manifest及audit。再使用现有rebuild_existing_apk.py和原发布签名脚本打包签名。新工具只允许指定10份同名Texture2D/Sprite资源；不同版本、未知对象或外部依赖直接终止。

本轮原始资源未纳入Git，仅在工作区保存工具/文档/小型JSON审计；资源副本和中间包在runtime/client_release20261025_jp中。后续重新从旧ActivityUI基线构建时，需再次叠加本清单，不能默认旧基线含有这8项替换。

## 2026-10-25 覆盖安装补记

用户重新连接模拟器后，20:05:20已将JP-Local包通过ADB streamed install -r覆盖安装成功，保留原应用数据。20:06:12重启本地服务，18080/29000/29001均可连接。本地继续保留X2_ACTIVITY_ANCHOR=1791648000验收偏移，当前斟鄩之邑；未改变正式服默认活动排期。
