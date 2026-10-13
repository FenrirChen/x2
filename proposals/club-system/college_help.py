# -*- coding: utf-8 -*-
"""提案片段: 879 ``C2L_HelpPowerSpeed``(公会助力 / 建筑加速协助)。

**这不是一个可以独立导入的模块**, 而是本目录 ``club.py`` 之外、需要并入上游
``src/x2server/player/college.py`` 的一小段代码 —— 因为 879 的处理逻辑属于那个文件里的
``CollegeService`` 类, 按本提案的惯例(共享文件不整体放出)只把这一小段摘出来。

接入点(共 3 处, 全部位于 ``src/x2server/player/college.py``):

  1. **模块级常量**: 把下面的 ``GOLD_ITEM`` / ``AI_HELP_PER_PARAM`` /
     ``AI_HELP_MIN_SECONDS`` / ``AI_HELP_REWARD_GOLD`` 加到模块顶部。
     (若该文件里已有等值金币常量, 直接复用, 不必重复定义。)
  2. ``CollegeService.handlers()``: 在返回集合里加 ``"C2L_HelpPowerSpeed"``(见文件末尾片段)。
  3. ``CollegeService.handle()``: 增加 ``elif name == "C2L_HelpPowerSpeed":`` 分支, 调用
     ``self._HelpPowerSpeed(...)``(见文件末尾片段), 并把它返回的 ``completed`` 并入
     ``L2C_UpLevelBuildingId`` 回包 —— 与 234/271 走同一套显式分支, 不能用 ``C2L_<Name>``
     通用分派(通用分派拿不到 ``completed``)。

依赖(均为 ``college.py`` 既有设施): ``QUEUE_KEYS`` / ``finish_expired`` /
``COLLEGE_ERROR_OPT`` / ``self._grant`` / ``self.economy.reward_bytes``。
880 的 schema(``HelpPowerSpeed`` / ``HelpPowerSpeedParam``)见 README 的「需要新增的协议」;
助力页建筑列表的读取端见本目录 ``club.py`` 的 ``ClubReader.kvs_values``。

背景(反汇编实证): 「求助」按钮走社团聊天(``ChatModule_SendClubChat`` ->
``ChatService.PublishMsgAsync``, 打到客户端 29001 节点), 服务端拦不到; 客户端**唯一**能
发到服务端的助力动作就是 879, 所以本地把它做成了助力入口。
"""

# ---------------------------------------------------------------------------
# 接入点 1: 模块级常量 (并入 src/x2server/player/college.py 顶部)
# ---------------------------------------------------------------------------

# 金币号 (economy.CURRENCIES 的 gold, item 1237901)。879「一键助力」回包要带奖励。
GOLD_ITEM = 1237901

# ---- 公会助力 (879/880, 建筑加速协助) ----------
# 本地口径: 玩家一旦发请求就立刻被人机回帮 —— 把**每一条 879 param 视为一次人机回帮**,
# 按玩家当前建造队列总工期的固定比例提前 endTime。比例 5%/次 * 40 人机 ≈ 全团回帮即可
# 完工; 单次助力也在小时级工地上有可见效果。提前到 now 即完工, 由 finish_expired 落地
# (与 234/271 同一套结算)。
AI_HELP_PER_PARAM = 0.05
AI_HELP_MIN_SECONDS = 60
# 「一键助力」(helpPower==2) 的奖励: 每帮一个成员给一点金币。客户端
# OnGetHelpPowerSpeed 在 helpPower==2 分支里 UIAPI_ShowGetAwardItem(rewardData),
# rewardData 为空时该调用会读到 null -> 必须带非空奖励 (见 880 schema 注释)。
AI_HELP_REWARD_GOLD = 500


# ---------------------------------------------------------------------------
# 接入点 2/3 的宿主: 下列方法需并入上游已有的 CollegeService 类体。
# 这里的 ``class CollegeService`` **只是片段占位**, 不要导入/实例化本文件。
# ---------------------------------------------------------------------------
class CollegeService:
    """片段占位类(真身上游 ``player/college.py`` 已有), 仅为让本文件语法自洽。"""

    def _HelpPowerSpeed(self, player_id: int, request: dict, state: dict, now: int,
                        values: dict, done: list[int]) -> list[int]:
        """879/880 公会助力: 玩家在助力页点「助力 / 一键助力」后, 人机立刻回帮。

        客户端链路 (反汇编实证):
          * WishListPage_BuildHelpNode_HelpButtonClick (0x13653A0) 对**他人**节点 ->
            CollegeModule_SendHelpBuidInfo (0x1B05874), 组装一条 HelpPowerSpeedParam
            {playerIded=被助力者, buildingId, buildingLevel}, helpPower=1;
          * 一键助力 WishListPage_BtnEventHelpAll -> SendHelpBuidInfoAll (0x1B05C08),
            把 [module+0x180] 里**除自己以外**的全部行各一条 param, helpPower=2。
          * 回包 880 由 OnGetHelpPowerSpeed (0x1B05FCC) 消化, 硬性要求: code==10;
            helpPowerSpeedParam 非空; helpPower∈{1,2}; ==2 时 rewardData 非空
            (UIAPI_ShowGetAwardItem) 且 CurrentHelpCount += param.Count。

        本地口径 (玩家一旦发请求就立刻被人机回帮):
          每条 param 记一次人机回帮, 帮的是**玩家自己**正在建造的队列 —— 本地只有玩家
          自己的 build_queue/wonder_queue 是真实的 (AI 的建造进度是 club 侧合成的展示数据,
          见 ClubReader.kvs_values)。提前量 = 该队列总工期 × AI_HELP_PER_PARAM × 回帮次数,
          至少 AI_HELP_MIN_SECONDS; 提前到 now 即完工, 由 finish_expired 落地, 完工 id 追加
          进 done 以便顶层的 L2C_UpLevelBuildingId 回包。请求里的 playerIded/buildingId 只
          用于回显, 不影响本地结算 (都是 AI 的合成建筑)。

        返回本次真正完工的 buildingId 列表 (含 done 原有的)。
        """
        params = list(request.get("helpPowerSpeedParam") or [])
        help_power = int(request.get("helpPower") or 0) or 1
        # 回包字段: helpPowerSpeedParam 原样回显 (客户端拿它做 Count 校验 / 计数),
        # helpPower 回显请求值 (缺省按"逐个助力"=1), helpPowerSpeed 本服不下发。
        values.update(helpPower=help_power, helpPowerSpeedParam=params)
        if not params:
            # 客户端对空列表直接 return, 但按它自己的错误码口径给个明确的 13, 避免回 10
            # 却不做任何事 (否则 CurrentHelpCount 会 +0 且 UI 无反馈)。
            values["code"] = COLLEGE_ERROR_OPT
            return done
        helpers = max(1, len(params))
        for key in QUEUE_KEYS.values():
            queue = state.get(key) or {}
            end = int(queue.get("endTime", 0))
            if not queue or end <= now:
                continue
            duration = int(queue.get("duration", 0)) or max(end - int(queue.get("startTime", now)), 0)
            cut = max(int(duration * AI_HELP_PER_PARAM * helpers), AI_HELP_MIN_SECONDS)
            queue["endTime"] = max(now, end - cut)
        completed = finish_expired(state, now)
        for building_id in completed:
            if building_id not in done:
                done.append(building_id)
        if help_power == 2:
            # 一键助力: 每帮一个成员给一份金币奖励 (客户端会弹奖励框)。
            rewards = {GOLD_ITEM: AI_HELP_REWARD_GOLD * helpers}
            self._grant(player_id, f"club-help:{player_id}:{now}", rewards)
            values["rewardData"] = self.economy.reward_bytes(rewards)
        return done


# ---------------------------------------------------------------------------
# 接入点 2/3 的调用侧片段 (照抄进上游 CollegeService 的对应位置)
# ---------------------------------------------------------------------------
#
# (a) handlers() —— 在返回的集合里加一项(与 881 相邻):
#
#       "C2L_HelpPowerSpeedValid",
#       # 879 公会助力 (建筑加速协助): 助力页的「助力 / 一键助力」按钮。回包 880 见
#       # _HelpPowerSpeed; 客户端唯一的助力入口 (求助按钮走聊天服务, 服务端拦不到)。
#       "C2L_HelpPowerSpeed",
#
# (b) handle() —— 在逐条 name 分派处(234/271 之后)加显式分支:
#
#       elif name == "C2L_HelpPowerSpeed":
#           # 879 助力: 人机把玩家自己的队列 endTime 提前; 若因此跑满, 完工 id 要用
#           # 本次请求的 completed 列表回包 (L2C_UpLevelBuildingId), 所以与 234/271
#           # 一样走显式分支, 不用通用分派 (通用分派拿不到 completed)。
#           completed = self._HelpPowerSpeed(player_id, request, state, now, values,
#                                            completed)
#
# 之后照旧: handle() 末尾把 completed 里的每个 id 发一条 L2C_UpLevelBuildingId。
