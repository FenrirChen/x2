# 提案：社团（公会）系统（本地实现，仅供评估）

> **这不是 PR**，也不是请求合并。这里只是把我在**本地单机 fork** 里已经跑起来的一套
> 「社团（公会）系统」实现放出来，供维护者评估。**要不要合进主仓库、怎么合，完全由你决定。**
> 代码直接搬过去不能跑，见下面的「接入方式」。

## 这是什么

客户端社团页是一套**混合协议**：**读**走 PBS HTTP（路由前缀 `/ClubService.`，POST+JSON，
响应信封 `{"error":"","code":0,"data":{...}}`），**写/操作**走 TCP 游戏消息
（`C2L_*`/`L2C_*`，号段 742..799，见 `protocol/recovered_ids.py`）。主仓库目前这两条都没有实现
（`analysis/coverage/` 里 `C2L_CreateClub`/`C2L_RecommandClub` 等仍是 `MISSING`；抓包
`logs/packets.jsonl` 里用户进社团页发的 `C2L_RecommandClub(744)`/`C2L_CreateClub(742)` 当时没有任何回包）。
本目录把它补上了。

具体功能（均已本地实测可用）：

- **创建社团**（`C2L_CreateClub`）与**推荐社团列表**（`C2L_RecommandClub`，分页下 `SimpleClubData`）。
- **申请加入**（`C2L_AppalyJoinClub`）/ **快速加入**（`C2L_QuickJoinClub`，`list<int32>`）。
- **审批**（`C2L_ClubApproval`）、**成员权限变更**（`C2L_UpdateMemberPrivilege`）、
  **踢人**（`C2L_DismissMember`）、**退会**（`C2L_QuitClub`）。
- **社团资料/招募设置**（`C2L_UpdateClubInfo` / `C2L_UpdateClubRecruit`）。
- **社团活动主数据**（`C2L_ClubActiMainData`：挑战次数、已领层、已战镜像分节）。
- **祈愿**：发愿（`C2L_ClubWishing`）、祈愿计数（`C2L_ClubWishingCount`）、
  捐赠（`C2L_ClubWishingDonate`）、领取（`C2L_ClubWishingReceive`）；人机会按延时来助力。
- **镜域试炼 boss + 结算**：镜域血池下发（`clubDamage_{层号}`）+ 挑战结算后推成员伤害榜/活动积分榜；
  客户端打完镜域不发 `PostClubBattle`，由 `battle.py` 的结算钩子自行推导（`settle_mirror_checkout`）。
- **榜单**（`/RankingService.QueryRank`）。
- **公会助力页建筑列表**（`/KVStoreService.GetValuesV2` 的 `club_speed_<uid>_1/2`）。

## 文件

| 文件 | 目标路径（主仓库内） | 说明 |
|---|---|---|
| `club.py` | `src/x2server/player/club.py` | 新增。`ClubReader`（PBS 读取端，表 `clubs/club_members/club_activity/club_wishes/...`）+ `ClubService`（TCP 操作端，应答 `C2L_*`） |
| `club_messages.py` | `src/x2server/messages/club.py` | 新增。`CLUB_IDS` 号段表 + `CLUB_SCHEMAS`（含 `SIMPLE_CLUB_DATA`） |
| `club_catalog.json` | `src/x2server/data/club_catalog.json` | 新增。社团招募/图标等静态配置 |
| `ai_players.json` | `src/x2server/data/ai_players.json` | 社团成员名册（复用好友系统同一份人机数据） |

## 需要新增的协议（参考）

这些目前登记在本地 `protocol/recovered_ids.py` 的 club 段，接入时需要一并加：

```
# C2L / L2C（消息号）
("CreateClub",             742, 743),
("RecommandClub",          744, 745),
("AppalyJoinClub",         746, 747),
("UpdateClubInfo",         748, 749),
("ClubApproval",           750, 751),
("UpdateMemberPrivilege",  752, 753),
("DismissMember",          754, 755),
("QuitClub",               756, 757),
("ClubActiMainData",       758, 759),
("ClubWishing",            762, 763),
("ClubWishingCount",       764, 765),
("ClubWishingDonate",      766, 767),
("ClubWishingReceive",     768, 769),
("QuickJoinClub",          786, 787),
("UpdateClubRecruit",      791, 792),
("JoinClubListner",        795, 796),
("ClubReceiveReward",      798, 799),
```

关键 schema（字段号=客户端 `protocol/commandx2_messages.json` 声明序）：

```
SIMPLE_CLUB_DATA = S("SimpleClubData", (
    F(1,"clubId",K.INT32), F(2,"name",K.STRING), F(3,"desc",K.STRING),
    F(4,"memNum",K.INT32), F(5,"memLimit",K.INT32), F(6,"score",K.INT32),
    F(7,"autoLevel",K.INT32), F(8,"applyLevel",K.INT32), F(9,"icon",K.INT32)))

"C2L_QuickJoinClub":        (F(1,"clubIds",K.INT32, repeated=True),)

# 坑: receivedLayer / battledSectionIds 在命令表里声明成 list<AppConfig>,
#     但真实语义是 list<int32>，必须按 repeated int32 编解码（见 club_messages.py docstring）。
"L2C_ClubActiMainData":     (F(1,"code",K.ENUM), F(2,"challegeCount",K.INT32),
                             F(3,"receivedLayer",K.INT32, repeated=True),
                             F(4,"scoreRewardFlag",K.INT32),
                             F(5,"battledSectionIds",K.INT32, repeated=True))
```

## 需要接入的共享文件（本地改过，未随本目录放出）

1. `src/x2server/messages/core.py`：把 `CLUB_SCHEMAS` 并进 `CORE_SCHEMAS`（`ClubService` 靠
   `CORE_MESSAGE_REGISTRY.name_for` 取名再解码）。
2. `src/x2server/bootstrap/local_identity.py`：加 `/ClubService.*`（社团页/推荐/祈愿页，动态应答）、
   `/RankingService.QueryRank`（社团排行，直接回合法 `QueryRankReply`）、
   `/KVStoreService.GetValuesV2`（公会助力页建筑列表）三条 HTTP 路由。
3. `src/x2server/player/college.py`：`879 C2L_HelpPowerSpeed` 公会助力（建筑加速协助），
   按 `/KVStoreService.GetValuesV2` 的 `club_speed_*` 键对接。
4. `src/x2server/player/battle.py`：镜域试炼（SectionType 12）结算钩子，调 `club.settle_mirror_checkout`。
5. `tools/local_game_server.py`：接线 `ClubReader`（挂到 identity 的 `club_reader`）与 `ClubService`
   （注册 `C2L_*` handler）。

## 已知限制

- 直接把 `club.py` 拷进去**不能跑**：它依赖上面的 `CORE_SCHEMAS` / HTTP 路由 / handler 接线与
  `battle.py` 镜域钩子，这几处是本地改过的共享文件，我没有一起放出来（会给主仓库带来大量无关 diff）。
- 镜域伤害→活动积分的换算比（`MIRROR_SCORE_DIV`）是本地自造，官方换算表未反出。
- 人机名册是本地数据，不是从官方表还原的。
- 没有配套单测。

## 状态

本地单机环境下已实测可用（创建/推荐/申请/审批/成员管理、祈愿收发、镜域 boss+结算、榜单、
公会助力页均正常）。再次强调：**这只是一份参考实现，合不合、怎么合由维护者定。**
