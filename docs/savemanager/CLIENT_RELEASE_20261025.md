# 2026-10-25 赛季实际入口资源补修

## 原因与修复范围

`BattlePassMainView.OnMBtnWanFaClick`（0x182B9AC）以参数12跳转章节模块，进入 `ChapterContent` 的 `UI_MapChoose/BattlePass` 页签。上一版只修改独立的 `UI_BattlePass_Farm`，没有修正这个真实入口。

- `UI_MapChoose`（c2688ba506c9bdf469ce1183e197a365）将九块月相标题中的主体替换为原包 `SaiJi_Main_ZhuTi3` 完整起源标题，关闭其余八块 Image。保留全部原对象、按钮、回调及动画绑定，仅调整标题比例。
- 关闭该页签两组明确属于月相的 `ui_yuexiang_hou01 (1)`、`ui_yuexiang_qian01 (1)` 装饰对象。
- 页签实际空白背景是 Image3450/WanFa_BG，不能误改共享 VideoBg3335。3450引用包内 `Season0BG` Sprite2，且不拦截点击。
- 赛季主页 `UI_BattlePass_Main` 的背景Image387引用同一张静态图；关闭其子级AVPro DisplayUGUI326，避免未加载视频的白色画布遮挡。保留MediaPlayer及原有代码引用。

这是**静态兼容背景**，未恢复原动态CG。`StartOuterPV`（0x1829314）从MediaPlayer读取 `Video/battlepassMain.mp4`，现有原包、旧修复包及模拟器数据中未找到该文件；它们仅有 `assets/Video/PV.mp4`，不能混作赛季CG。

## 打包与验证

最终两包路径：`D:/demo/x2/逆向/打包/X2-Revival-ClientFix20261025-{Local,Remote}-signed.apk`。

- Local SHA256：f859668408c88ef7fd05f91cf58ab50d3cd10bfb2fcc580eb569723c4e084969。
- Remote SHA256：ef6ba2683ce155b6f48041d86ab2beff80dba725d9c0061414a214fa961523d9。
- 每包2147354451字节；沿用原发布证书，v1/v2/v3验签通过。
- 对比20261024基线，仅上述两份Unity资源文件变化；原生库、六星补丁、语音桥、存档管理DEX、Unity库、服务器地址均保持一致。全部ZIP CRC和4字节对齐检查通过。
- 资源往返序列化检查保留所有对象；非白名单对象原始字节保持一致。构建入口接入 `patch_origin_chapter_tab.py`，后续从旧基线重建亦不会遗漏真实章节入口。

## 尚未完成

面板重叠：用户确认暂时无法复现，没有按猜测修改布局。

活动缺图不能算全部修好。实机斟鄩之邑背景已显示，但Title329仍是空Sprite，形成白色标题区域。遍历原APK中含ZhenXun命名的51个资源条目，只找到UI图集组件、章节图与共享资源中的72×80入口标题，尚未定位到原活动页完整大标题。未拿入口小图冒充完整标题，也未把CG背景修复表述为全部组件修复。后续仍需补齐相应原资源或明确采用兼容组件方案。

## 最终实机复核

2026-10-25 12:11:32，MuMu 127.0.0.1:7555覆盖安装最终Local包成功，原应用数据保留。使用已保存revival账号登录成功；赛季主页显示静态Season0BG，实际章节页签同样显示背景与起源标题，月相装饰不再显示。标题需等待正常入场动画完成，不能将动画中的暂时隐藏误判为丢失。最新日志确认title voice: played，未检出Unity空引用异常。本地服务端在12:11:26重启，三个端口可连接。未执行购买、战斗或修改存档进度。
