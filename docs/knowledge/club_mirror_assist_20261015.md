# 单机社团镜域成员助战（2026-10-15）

## 用户指定规则
玩家每次完成镜域战斗后，实际入团的 NPC 成员（不含玩家）按角色 ID 排序，各行动一次，每次伤害为玩家本局对 BOSS 总伤害的 90%，整数向下取整。每次行动最多扣除当前 BOSS 剩余血量，击杀的溢出伤害丢弃；下一名成员攻击下一只 BOSS。未入团好友不参与；成员行动不额外消耗玩家挑战次数。助战只沿「常驻 1~36 + 当周这 4 层」这条链推进，打完就停，不跨周目组（见 club_mirror_rounds_20261030.md）。

## 客户端协议证据
- C2L_CheckoutMainMission.hp 为字段 28、int64，尽管名称为 hp，内容是伤害。原生 FightModule.Send 在 0x14424F8 调用 GetTotalHurtToBoss，将结果写入对象偏移 +0xB8。
- C2L_CheckoutMainMission.Serialize 0x3A553C4 起写 tag e0 01（28号字段），0x3A55420 读取 +0xB8 后 WriteUInt64。未修改 APK。
- ClubModule.GetClubBossHP 0x15643CC：当前最大血量减去 Meta[clubDamage_{当前零基层+1}]。
- ClubModule.GetClubActivityLayer 0x1560E28：从正值 clubLayer_N 元数据推导推进层数，N 使用一基层号而非 BossID。
- LoadingHelper.GetSingleGameSceneData 调用 GetClubBossHP，故元数据同时供界面与下一场战斗初始化使用。

## 状态和结算
镜域剩余血量、逐次助战明细、已处理 run 标记存于原 activity_state/singleplayer-social，不新增导出存档遗漏的数据表。结算与战斗奖励 receipt 同一事务提交，重试不重复造成伤害；篡改重试沿用既有冲突拒绝。失败或时间结束但产生实际伤害的结算也计入伤害；success 本身不强行清空血量。

新客户端按显式 hp 计数，hp=0 不造成伤害。兼容旧报文：省略 hp 且 success=true 时，以击杀所证明的剩余血量作为本局伤害；省略且失败则为零。仅允许当前层进入战斗（额外层还要求属于当周这 4 层），击杀后才推进，保留原有挑战次数日恢复规则。

所有已击败层均进入原 ClubReceiveReward 的可领奖集合，领取仍需操作且只能一次；不会替 NPC 额外发放个人战斗掉落。结算前同步 L2C_ClubActiMainData，原生界面打开时 GetSelfClub 取得新的层数和血量元数据。

## 血量依据
新增 club_mirror_health.json，按原生 GetClubBossMaxHP 0x1563EF4 的 PlayerAttrib + MapInfo.MonsterLevel + MonsterLevelBonus 公式预计算 52 个 BOSS；保存表来源 SHA256、原始血量、倍率、等级与计算结果。等级小于36采用千分比，否则整数倍率。排除旧 club_catalog.stageIds 中不存在的关卡别名（例如 1）。

## 验证
31 项镜域及社团测试通过：三名 NPC 的 40/36/24/36 样例验证溢出丢弃和接力；玩家先击杀、末层停止、无人入团、零伤害、跨战斗剩余血量、重复结算、协议字段28、领奖、实例重建后保留数据、52层血量，以及社团其他既有功能。
