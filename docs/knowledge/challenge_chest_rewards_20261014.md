# 现世复刻战利品箱漏发修复（2026-10-14）

原有 SectionRewardCatalog 保留101个E_Challenge关卡的ChestReward/ExpertChestReward字段，但EconomyService.settle只处理FirVReward/VReward及outsideItems，遗漏了这两个固定箱子物品。掉落预览由客户端额外追加箱子，因而预览可见、正常结算却从不发放。

原生证据：ChapterInfoView.ShowDropItem RVA0x165A2FC，0x165AA14确认Type=2；0x165AA28/0x165AA40读取SectionTable.ChestReward(+0x11C)/ExpertChestReward(+0x118)。0x165AA58读取ChallengeTask.expertMode，0x165AA68–0x165AA78按普通/专家选一项加入预览，二者不是Gift组，也不是同时领取两箱。预览本身没有给出概率公式；服务端将关卡成功通关的箱子奖励补入每局固定结算。

实现：只对实际成功通关、配置了箱子的E_Challenge关卡发放1个对应战利品箱。模式从入场时持久化的L2C_FightData读取，不信任结算上报expertMode；普通发ChestReward，专家发ExpertChestReward。客户端若在outsideItems回报了这两种箱子，会移除该回报并统一按服务器固定数量发一次，防止重复或数量伪造。失败/退出、不配置箱子的关卡不发；新的成功战斗可再次获得，已有BattleService UUID receipt阻止同局重放二次发放。专家箱同时记录E_GetExpertChest(42)事件。

箱子进入背包，使用既有Item.Used→bag_client_catalog.Gift随机奖励链。未改箱内奖励概率、兽主预算和其它关卡奖励；不开箱不自动拆奖。旧存档不进行无证据的历史补发，因为旧客户端outsideItems可能存在真实箱子记录，必须逐run审计后再决定补偿。

测试覆盖全部101关的两种模式物品和Used链接，多章节普通/血月真实入战结算，模式伪造、99个箱子回报去重、失败不发、新局重复挑战可得、同局重放不可重复及实际背包开箱。
