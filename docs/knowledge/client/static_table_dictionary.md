---
Document-Type: Current Knowledge
Domain: Client
Status: AUTHORITATIVE
Updated: 2026-09-25
Generated-By: tools/analysis/build_table_dictionary.py
---

# 客户端静态表数据字典（265 张注册表）

来源：ResourceManager 注册表 + APK 原字节解码（`analysis/drop_archaeology/`）。
机器可读全文：`analysis/static_dictionary/tables.json`（每表字段统计/主键候选/引用候选）。

| 表 | 记录数 | 域 | 主键候选 | 关键引用 | 状态 |
|---|---:|---|---|---|---|
| achievement | 318 | Achievement | AchievementConditionID,AchievementDescribe | AchievementDescribe→LanguageKey(1.0); AchievementID→Achievement(1.0) | DECODED |
| achievementcondition | 461 | Achievement | AchievementConditionID | CompleteNum→ShopGroup(0.69) | DECODED |
| achievementconditionline | 71 | Achievement | AchievementConditionID | — | DECODED |
| collection | 26 | Achievement | CollectionID,GiftGroup | CompleteValue1→Unit(1.0); GiftGroup→Gift(1.0) | DECODED |
| collectiondisplay | 102 | Achievement | CollectionDisplayID | CollectionDisplayID→LanguageKey(0.402); Describe1→LanguageKey(1.0) | DECODED |
| illustration | 77 | Achievement | HelpID | TitleID→LanguageKey(0.959) | DECODED |
| medal | 75 | Achievement | MedalDescribe,MedalID | AttribId→PassiveSpell(1.0); MedalDescribe→LanguageKey(1.0) | DECODED |
| activity | 1 | Activity |  | — | DECODED |
| activitybox | 27 | Activity | BoxID | BoxID→CurrencyType(1.0); BoxName→LanguageKey(0.524) | DECODED |
| activitybuilding | 16 | Activity | BuildingEffectDes | BuildingClue→Item(1.0); BuildingDes→LanguageKey(1.0) | DECODED |
| activityexchange | 1 | Activity |  | — | DECODED |
| activityreal | 141 | Activity | ActivityID | ActivityGroup→ShopGroup(0.674); ActivityReward→Gift(0.412) | DECODED |
| answerconfig | 564 | Activity,System | QaID | AnswerName→LanguageKey(0.878); AnswerReward→Gift(0.939) | DECODED |
| bloodmoonconfig | 1 | Activity |  | — | DECODED |
| bloodmooninfo | 9 | Activity | ChapterID,ChapterName | ChapterModuleReward→Gift(1.0); ChapterName→LanguageKey(0.889) | DECODED |
| bloodmoonmodule | 580 | Activity | ID | DescID→LanguageKey(1.0); ModuleEffect→PassiveSpell(0.964) | DECODED |
| dairyresource | 2 | Activity |  | — | DECODED |
| gameactivity | 7 | Activity | ID | ID→ExtraDroop(0.714); RegistrationDay→ShopGroup(1.0) | DECODED |
| lightyardcontrol | 1 | Activity |  | RoomNumber→ShopGroup(1.0); RoomUnlockLevel→ShopGroup(0.625) | DECODED |
| monopolygrid | 51 | Activity | GridID | GoblinGridReward→Gift(1.0); GridID→ShopGroup(0.608) | DECODED |
| mooncamp | 4 | Activity | CampDescribe,CampID | CampDescribe→LanguageKey(1.0); CampInfo→LanguageKey(1.0) | DECODED |
| moonequip | 24 | Activity | EquipID,EquipItemID | EquipEffect→PassiveSpell(1.0); EquipInfo→LanguageKey(1.0) | DECODED |
| moonnpc | 20 | Activity | NPCDefaultTalk,NPCID | NPCGift→Gift(0.952); NPCID→Unit(1.0) | DECODED |
| newyearcafe | 90 | Activity | ID | CafeName→LanguageKey(1.0); CafeUnlockCon→Item(1.0) | DECODED |
| newyearcook | 11 | Activity | TargetFood | ChefItem→Item(1.0); ConfigID→ShopGroup(1.0) | DECODED |
| newyearfood | 35 | Activity | ProductID,RecipeID | CafeExp→ShopGroup(0.625); ItemGroup→Item(1.0) | DECODED |
| redpackage | 3 | Activity |  | — | DECODED |
| returncontrol | 2 | Activity |  | ActiveGift→Gift(1.0); AgainSign→Gift(1.0) | DECODED |
| seasonconfig | 400 | Activity | ID | Level→ShopGroup(0.64); SectionGroup→Section(1.0) | DECODED |
| sharemessage | 13 | Activity | ShareID | ShareWeibo→LanguageKey(1.0) | DECODED |
| simpleactivity | 1 | Activity |  | ExtraGiftList→Gift(1.0); GiftList→Gift(1.0) | DECODED |
| simpleactivityaction | 4 | Activity | ActivityActionID,ParmMax | — | DECODED |
| accountbuff | 57 | Battle,Player | AccountBuffID,AccountContentID | AccountContentID→LanguageKey(1.0); AccountEffectValue1→Tower(0.5) | DECODED |
| attribtype | 119 | Battle | AttribId,NameId | AbilityRate→Tower(0.8); AttribId→ShopGroup(0.756) | DECODED |
| battlefavorability | 3 | Battle,Friend |  | — | PARSED_NO_SCHEMA |
| battlepass | 3 | Battle |  | BpTaskOpenWeek→ShopGroup(0.545); BpTaskRandom→MonsterEventTable(0.933) | DECODED |
| battlepassachievement | 212 | Battle,Achievement | AchievementConditionID,AchievementDescribe | AchievementDescribe→LanguageKey(1.0); AchievementName→LanguageKey(1.0) | DECODED |
| battlepassachievementcondition | 79 | Battle,Achievement |  | — | PARSED_NO_SCHEMA |
| battlepassartifact | 5 | Battle,Hero | ArtifactSlotID,CostItem | ArtifactEffectValue→ShopGroup(0.684); ArtifactSlotID→ShopGroup(1.0) | DECODED |
| battlepassaward | 12 | Battle | GiftID,ID | GiftID→Gift(1.0); ID→ShopGroup(1.0) | DECODED |
| battlepasslevel | 1300 | Battle | ID | GiftGroup01→Gift(1.0); GiftGroup02→Gift(1.0) | DECODED |
| battlepassmilestone | 4 | Battle | MilestoneID | DataDisplay→LanguageKey(1.0); DataDisplayAll→LanguageKey(1.0) | DECODED |
| battlepassmiracle | 3 | Battle,Roguelite |  | — | DECODED |
| battlepassrank | 81 | Battle | ID,RankID | MinLayer→ShopGroup(0.6); RankName→LanguageKey(1.0) | DECODED |
| battlepasstalent | 15 | Battle | TalentID,TalentName | AttribId→ShopGroup(0.857); DisplayNumbers→Tower(0.556) | DECODED |
| battlepasstalentgroup | 9 | Battle | GroupID | — | DECODED |
| battlepasstask | 108 | Battle,Task | BattlepassTaskID,TaskConditionID | ExpValue→ShopGroup(0.667); GiftGroup→Gift(1.0) | DECODED |
| battlepassunit | 3 | Battle |  | PassiveID→PassiveSpell(1.0) | DECODED |
| cardbuff | 5 | Battle,Draw | ID | — | DECODED |
| combo | 261 | Battle | HitLimite,ID | BuffID→LanguageKey(0.96); ComboImgIndex→ShopGroup(1.0) | DECODED |
| continuefightbase | 11 | Battle | ContinueFightID | ContinueFightID→ShopGroup(1.0) | DECODED |
| damagetable | 712 | Battle | ID | DamageType2→ShopGroup(0.833); SkillID→Skill(0.996) | DECODED |
| dynamicgradesuppression | 90 | Battle | LevelDifference | LevelDifference→ShopGroup(0.656); PlayerPassive→PassiveSpell(1.0) | DECODED |
| herodamagefactor | 26 | Battle,Hero |  | — | PARSED_NO_SCHEMA |
| memorybuff | 26 | Battle,Mission | ID | BuffCost→ShopGroup(1.0); BuffEffect→PassiveSpell(1.0) | DECODED |
| monstereventgroup | 1948 | Battle | EventGroupID | EventGroupID→MonsterEventGroup(1.0); EventList→MonsterEventTable(0.999) | DECODED |
| monstereventtable | 2630 | Battle,System | EventID | EventID→MonsterEventTable(1.0); MonsterID→Unit(1.0) | DECODED |
| monsterwave | 41 | Battle | ID | LevelUp→ShopGroup(0.889); MonsterEvent→MonsterEventGroup(1.0) | DECODED |
| newyearcafebuff | 34 | Battle,Activity | ID,Name | Desc→LanguageKey(1.0); DescSimple→LanguageKey(1.0) | DECODED |
| npcevent | 408 | Battle | NPCEventID | ButtonText→LanguageKey(1.0); EventValue2→Unit(0.4) | DECODED |
| optioneffect | 102 | Battle,System | OptionID | EffectParm1→Unit(0.846); EffectParm2→ShopGroup(0.439) | DECODED |
| passivespellenhance | 42 | Battle | PassiveBD | DestList→PassiveSpell(1.0); SrcList→PassiveSpell(1.0) | DECODED |
| passivespelltb | 2286 | Battle | PassiveID | PassiveID→PassiveSpell(1.0) | DECODED |
| profrestraint | 8 | Battle | ID | ID→Tower(0.5) | DECODED |
| saneffect | 10 | Battle,Player | DescID,MsgTipsID | DescID→LanguageKey(1.0); Effects→PassiveSpell(1.0) | DECODED |
| titofightguidetable | 55 | Battle,Guide | ID | ID→Skill(0.982); NextID→Skill(1.0) | DECODED |
| towereffect | 16 | Battle,Tower | EffectConditionDescribe,EffectDescribe | EffectAction→PassiveSpell(1.0); EffectConditionDescribe→LanguageKey(1.0) | DECODED |
| trialunitbase | 20 | Battle,Challenge | TrialHeroID | AppearanceID→Item(1.0); ArtifactStar→ShopGroup(1.0) | DECODED |
| unitbase | 1912 | Battle | ID | AIBehaviac→Unit(0.985); ActionFileID→Unit(0.986) | DECODED |
| x2buffbase | 1102 | Battle | ID | EffectiveTime→ShopGroup(0.556); Layer→ShopGroup(1.0) | DECODED |
| escort | 3 | Challenge |  | MonsterEvent→MonsterEventGroup(1.0) | DECODED |
| snatch | 8 | Challenge | SnatchID | NPCUnitID→Unit(1.0) | DECODED |
| brinkconversation | 202 | Chat | TalkingID | NeedCharacter→Unit(1.0); TalkingBubble→LanguageKey(1.0) | DECODED |
| brinkconversationstory | 51 | Chat | TalkingGroup | TalkingCharacter→Unit(1.0); TalkingID→LanguageKey(0.954) | DECODED |
| bubbletalk | 2574 | Chat | BubbleID | BubbleID→LanguageKey(1.0); BubbleRandom→Tower(0.462) | DECODED |
| chatcontrol | 1 | Chat,System |  | — | PARSED_NO_SCHEMA |
| chatlink | 5 | Chat | ChatDesc,ChatLinkID | ChatDesc→LanguageKey(1.0) | DECODED |
| conversation | 16665 | Chat | ConversationID | — | DECODED |
| dubbing | 1422 | Chat | DubbingId | DubbingName→LanguageKey(1.0); DubbingText→LanguageKey(1.0) | DECODED |
| dubbingcondition | 39 | Chat | Fighting,GetHero | HeroId→Unit(1.0) | DECODED |
| collegebuilding | 16 | College | DescEnID,DescID | DescEnID→Unit(0.5); DescID→LanguageKey(1.0) | DECODED |
| collegecustomer | 42 | College | CustomerID,Name | ChatDesc→LanguageKey(1.0); ChatNegativeDesc→LanguageKey(1.0) | DECODED |
| collegeexplore | 15 | College | DescID,ID | DescID→LanguageKey(1.0); Exp→ShopGroup(0.786) | DECODED |
| collegelevel | 555 | College | BuildID | BuildingLevel→ShopGroup(0.75); Consume→Item(1.0) | DECODED |
| collegestarlevel | 95 | College | BuildID | BuildingStar→ShopGroup(1.0); Consume→Item(1.0) | DECODED |
| currencydisplay | 53 | Currency | DisplayID | DisplayID→ShopGroup(0.623) | DECODED |
| currencytype | 46 | Currency | Desc,LangueID | Desc→LanguageKey(0.891); ItemID→Item(1.0) | DECODED |
| activitydungeon | 105 | DailyDungeon,Activity | ID | ActivityParam4→Item(0.615); ChallengeLevel→Section(0.994) | DECODED |
| dailydungeon | 25 | DailyDungeon | ID | DungeonDesc→LanguageKey(0.955); DungeonName→LanguageKey(0.87) | DECODED |
| endlessdungeontask | 17 | DailyDungeon,Task | EndlessDungeonTaskID,OrderIndex | GiftGroup→Gift(1.0); OrderIndex→ShopGroup(0.765) | DECODED |
| taskendlessweek | 54 | DailyDungeon,Task | EndlessWeekTaskID | EndlessWeekTaskID→LanguageKey(0.444); GiftGroup→Gift(1.0) | DECODED |
| weeklydungeon | 5 | DailyDungeon | ID | ID→WeeklyDungeon(1.0); OpenCycle→ShopGroup(0.6) | DECODED |
| card | 60 | Draw | CardID,Describe | CardID→ShopGroup(0.667); Describe→LanguageKey(1.0) | DECODED |
| cardpassive | 59 | Draw | PassiveID | ActionCondition1→ShopGroup(0.667); ActionCondition2→ShopGroup(1.0) | DECODED |
| cardpregroup | 0 | Draw |  | — | None |
| drawparam | 48 | Draw | DrawnID | CommonPrize→Gift(1.0); ItemConsum→ShopGroup(1.0) | DECODED |
| drawrules | 48 | Draw | DrawnID | DrawnDesc→LanguageKey(1.0); DrawnDesc02→LanguageKey(1.0) | DECODED |
| dropbase | 6 | Drop | Divisor,ID | Divisor→ShopGroup(1.0); ID→ShopGroup(1.0) | DECODED |
| dropprop | 332 | Drop | DropClass | DropClass→DropClass(1.0); Group→ShopGroup(0.857) | DECODED |
| extradroop | 26 | Drop | ID | ExtraDisplayID→Item(1.0); ExtraDisplayShow→Item(1.0) | DECODED |
| collegeequibreset | 5 | Equipment,College | ID | EquibReastItem1→Item(1.0); EquibReastItem2→Item(1.0) | DECODED |
| equibattrib | 384 | Equipment |  | AttrType→ShopGroup(0.938); EquibRare→ShopGroup(1.0) | DECODED |
| equibattribbd | 66 | Equipment | AttrbdID | EquibQuality→ShopGroup(1.0); MainAttr→ShopGroup(0.722) | DECODED |
| equibbase | 126 | Equipment | EquibId | EquibId→Item(0.857); EquibPart→ShopGroup(1.0) | DECODED |
| equibexp | 16 | Equipment |  | EquibLevel→ShopGroup(1.0); NeedExp→ShopGroup(0.467) | DECODED |
| equibstage | 6 | Equipment | EquibValue,Exp | Exp→ShopGroup(0.833); ExpBonus→Tower(0.667) | DECODED |
| equibsuit | 20 | Equipment | NameID,SuitAttr1ID | NameID→LanguageKey(1.0); PassiveID→PassiveSpell(1.0) | DECODED |
| fishing | 5 | Fishing | FishingID | FishingID→ShopGroup(1.0); FishingPosition→ShopGroup(0.6) | DECODED |
| callwords | 5 | Friend | MainID | Index→ShopGroup(1.0) | DECODED |
| emojicontrol | 41 | Friend | EmojiId,EmojiName | EmojiId→ShopGroup(0.488); EmojiName→LanguageKey(1.0) | DECODED |
| favorabilityblog | 174 | Friend | BlogContent,BlogID | CommentHero→Unit(0.971); HeroID→Unit(1.0) | DECODED |
| favorabilitydairy | 118 | Friend | Dairy,DairyID | Date→ShopGroup(0.667); HeroID→Unit(1.0) | DECODED |
| favorabilitydate | 100 | Friend | DateID | DateID→LanguageKey(0.75); HeroID→Unit(1.0) | DECODED |
| favorabilityfetters | 156 | Friend |  | AttribValue→ShopGroup(0.526); Attribid→ShopGroup(1.0) | DECODED |
| favorabilityfiles | 742 | Friend | FilesContent,FilesID | FilesSubTitle→LanguageKey(1.0); HeroID→Unit(1.0) | DECODED |
| favorabilityhero | 39 | Friend,Hero | HeroID,PictureItem | HeroID→Unit(1.0); PictureItem→Item(1.0) | DECODED |
| favorabilityidcontrol | 36 | Friend |  | — | PARSED_NO_SCHEMA |
| favorabilitylevel | 20 | Friend | FavorLevel | BreakItemNum→ShopGroup(1.0); FavorLevel→ShopGroup(1.0) | DECODED |
| friendlevel | 4 | Friend |  | — | DECODED |
| functionopen | 84 | Guide | ID | ChineseNameID→LanguageKey(1.0); GuideId→ShopGroup(0.943) | DECODED |
| jump | 377 | Guide | JumpID | — | DECODED |
| msgtips | 6 | Guide | MsgTypeID | MsgTypeID→ShopGroup(1.0) | DECODED |
| tips | 34 | Guide | TipsID | TipsContent→LanguageKey(1.0) | DECODED |
| titoguidetable | 116 | Guide | ID | BlockID→LanguageKey(0.846); DelayTime→Tower(0.571) | DECODED |
| guildchallengeinfo | 52 | Guild,Challenge | BossID,BossName | BossName→LanguageKey(1.0); DifficultyLevel→ShopGroup(0.615) | DECODED |
| guildlevel | 1 | Guild |  | — | DECODED |
| guildpicture | 8 | Guild,Inventory | GuildPictureID | — | DECODED |
| guildwish | 61 | Guild | ItemID | ContributeAward→Gift(1.0); ItemID→Item(1.0) | DECODED |
| artifactbase | 40 | Hero | ArtifactDesc,ArtifactDetail | ArtifactDesc→LanguageKey(0.975); ArtifactDetail→LanguageKey(0.975) | DECODED |
| artifactfuse | 28 | Hero |  | AdvancedItem→Item(1.0); FuseID→ShopGroup(1.0) | DECODED |
| collegewonderskill | 54 | Hero,College | AddID,DescID | AttributeType→ShopGroup(0.833); DescID→LanguageKey(0.889) | DECODED |
| constellation | 12 | Hero | ConstellationID,ConstellationName | ConstellationID→ShopGroup(1.0); ConstellationName→LanguageKey(1.0) | DECODED |
| constellationcontent | 4392 | Hero | DateAndConstellation | AccountBuffID→Item(1.0); AccountBuffID1→Item(1.0) | DECODED |
| godhole | 35 | Hero | HeroID,SkillID | HeroID→Unit(1.0); ItemID→Item(1.0) | DECODED |
| herolable | 15 | Hero | LabelId,LangueID | EnglishNameID→Unit(1.0); LabelId→ShopGroup(0.667) | DECODED |
| jewelbase | 115 | Hero | JewelID | DustValue→ShopGroup(0.48); EffectValue1→ShopGroup(0.436) | DECODED |
| playerattrib | 1182 | Hero | ID | ChipPropID→Item(1.0); Damage→ShopGroup(0.512) | DECODED |
| playerstage | 46 | Hero | HeroStage | BigStarMax→ShopGroup(1.0); BigStarNum→ShopGroup(1.0) | DECODED |
| skillbase | 1333 | Hero | ID | CastDistanceMax→ShopGroup(0.478); Consume→Tower(0.545) | DECODED |
| skillhelper | 396 | Hero | UnitId | — | DECODED |
| skilllevel | 2155 | Hero |  | GrowCond→ShopGroup(0.532); Item→Item(1.0) | DECODED |
| skilllive2d | 91 | Hero,System | HeroID | HeroID→Unit(1.0) | DECODED |
| starchartsbase | 10 | Hero | DescID,ID | DescID→LanguageKey(1.0); NameEnglishID→LanguageKey(1.0) | DECODED |
| starchartsparam | 1 | Hero |  | DefultRelic→Item(1.0) | DECODED |
| starchartsskill | 17 | Hero | DescStoryID,NameID | DescID→LanguageKey(1.0); DescStoryID→LanguageKey(1.0) | DECODED |
| unitenum | 9 | Hero | UnitTypeID | — | DECODED |
| unitstyle | 18 | Hero | UnitId | UnitId→Unit(1.0) | DECODED |
| appearance | 227 | Inventory | AppearanceID | AppearanceID→Item(0.507); CardPaintingScale→ShopGroup(0.765) | DECODED |
| collegerecipe | 60 | Inventory,College | ProductID,RecipeID | Exp→ShopGroup(1.0); ItemGroup→Item(1.0) | DECODED |
| decoration | 12 | Inventory | DecorationDescribe,DecorationID | — | DECODED |
| indexinfo | 19 | Inventory | AttrID,ID | AttrID→ShopGroup(1.0); ID→ShopGroup(1.0) | DECODED |
| item | 3026 | Inventory | ItemID | DescID→LanguageKey(0.972); HistoryID→LanguageKey(0.987) | DECODED |
| itemgetandconsume | 2 | Inventory |  | — | PARSED_NO_SCHEMA |
| itemsource | 234 | Inventory | ItemID | ItemID→Item(1.0); SourceDesc→LanguageKey(1.0) | DECODED |
| picture | 155 | Inventory | PictureID | PictureDescribe→LanguageKey(1.0); PictureID→Item(0.994) | DECODED |
| pictureframe | 7 | Inventory | DescID,NameID | DescID→LanguageKey(1.0); NameID→LanguageKey(1.0) | DECODED |
| propertychange | 44 | Inventory |  | — | PARSED_NO_SCHEMA |
| readingiteminfo | 67 | Inventory | ID,LanguageTalkID | — | DECODED |
| recipe | 143 | Inventory | ProductID,RecipeID | ItemGroup→Item(1.0); ProductID→Item(0.888) | DECODED |
| eventnotice | 144 | Mail,Activity | ID | NoticeLanguage→LanguageKey(1.0); NoticeLanguage1→LanguageKey(1.0) | DECODED |
| mailconfig | 47 | Mail | GroupID,SenderName | SenderName→LanguageKey(1.0) | DECODED |
| mailinfo | 246 | Mail |  | — | PARSED_NO_SCHEMA |
| noticecontrol | 5 | Mail | NoticeID | ConditionNumber→Item(0.6) | DECODED |
| noticeevent | 15 | Mail,Activity | EventID | EventValue→ShopGroup(1.0) | DECODED |
| privatemail | 4034 | Mail | PrivateMailID | HeroID→Unit(1.0) | DECODED |
| privatemailcontrol | 4 | Mail | HeroID | HeroID→Unit(1.0) | DECODED |
| privatemailsystem | 5 | Mail | PrivateMailID,TextContent | TextContent→LanguageKey(1.0) | DECODED |
| pushmessage | 11 | Mail | PushID,PushMsg | PushMsg→LanguageKey(1.0); PushTime→ShopGroup(1.0) | DECODED |
| adventurelist | 8 | Mission | ID,Language | ID→ShopGroup(1.0); Language→LanguageKey(1.0) | DECODED |
| chapterinfo | 13 | Mission | ChapterNumber,MapTypeID | ChallengeLevel→Section(1.0); ChapterName→LanguageKey(1.0) | DECODED |
| collegequest | 120 | Mission,College | QuestID | AwardGroup→Gift(0.957); Hero→Unit(1.0) | DECODED |
| fixmapbase | 1246 | Mission | FixMapID | — | DECODED |
| mapinfo | 3099 | Mission | MapTypeID | Audio→Unit(1.0); MapTypeID→Map(1.0) | DECODED |
| maptrigger | 717 | Mission | TriggerID | Filtration→Unit(0.617); TaskID→ShopGroup(1.0) | DECODED |
| mazeindepexp | 48 | Mission |  | EndlessSectionID→WeeklyDungeon(1.0); Exp→Tower(0.727) | DECODED |
| missionpredecessor | 144 | Mission | PredecessorID | — | DECODED |
| missiontable | 193 | Mission | Complete,Desc | Award→Gift(1.0); Complete→LanguageKey(0.461) | DECODED |
| moonworldmap | 12 | Mission,Activity | LevelID,LevelName | ArriveLevel→ShopGroup(1.0); LevelDescribe→LanguageKey(1.0) | DECODED |
| povchapterinfo | 22 | Mission | ChapterID,ChapterNameID | ChapterHeroID→Unit(1.0); ChapterNameID→LanguageKey(1.0) | DECODED |
| quest | 1098 | Mission | QuestID | AimFloor→ShopGroup(1.0); AimNPC→Unit(0.978) | DECODED |
| questionnairenew | 20 | Mission,Activity | ID | ID→Unit(0.9); LoginDay→ShopGroup(1.0) | DECODED |
| scenebase | 13923 | Mission |  | BranchNum→ShopGroup(0.8); BranchRandom→ShopGroup(0.4) | DECODED |
| scenedisplay | 2 | Mission |  | — | DECODED |
| sceneskin | 4 | Mission | SceneSkinID | TimePartEnd→ShopGroup(1.0) | DECODED |
| sectionglobalparam | 16 | Mission | ID | ID→ShopGroup(1.0); SectionIDGroup→Section(1.0) | DECODED |
| sectiontable | 3203 | Mission | SectionID | AssistParam→Unit(0.905); ChallengeDesc→LanguageKey(1.0) | DECODED |
| taskchapter | 260 | Mission,Task | ChapterTaskID,TaskDescribe | DPPoint→ShopGroup(1.0); LastTask→TaskCondition(0.429) | DECODED |
| device | None | Player |  | — | ERROR |
| namelist | 3 | Player |  | — | DECODED |
| roleexp | 120 | Player | RoleLevel | GiftID→Gift(1.0); PowerNum→ShopGroup(0.721) | DECODED |
| sanconfig | 2 | Player |  | Effect→ShopGroup(1.0) | DECODED |
| santrigger | 80 | Player | SanTriggerID | SanTriggerID→ShopGroup(0.613); Select→ShopGroup(1.0) | DECODED |
| statisticalinformation | 7 | Player,System |  | — | PARSED_NO_SCHEMA |
| activityboxgoods | 693 | Reward,Shop,Activity | GoodsGroupID | BuyTimes→ShopGroup(0.75); GoodsGroupID→ShopGroup(0.654) | DECODED |
| battlepassexrankreward | 13 | Reward,Battle | GiftID,ID | GiftID→Gift(1.0); ID→ShopGroup(1.0) | DECODED |
| battlepassrankreward | 87 | Reward,Battle | ID | GiftID→Gift(1.0); ID→ShopGroup(0.644) | DECODED |
| boxconfig | 60 | Reward | BoxDesc,BoxID | BoxDesc→LanguageKey(1.0); BoxReward→Gift(1.0) | DECODED |
| constellationgift | 2 | Reward,Hero |  | AprilGift→Gift(1.0); AugustGift→Gift(1.0) | DECODED |
| gift | 10930 | Reward | GiftGroup | GiftGroup→Gift(1.0); GiftValue→Item(0.95) | DECODED |
| giftpackage | 237 | Reward | GiftPackageID | GiftID→Gift(1.0); GiftLabel→ShopGroup(0.8) | DECODED |
| giftpackagepush | 28 | Reward | GiftPackageID | PushParam2→ShopGroup(0.75); PushParam3→ShopGroup(0.5) | DECODED |
| monsterlevelbonus | 1000 | Reward,Battle | MonsterLevel | DamageLevelBouns→ShopGroup(0.597); MonsterLevel→ShopGroup(0.65) | DECODED |
| playerlevelbonus | 120 | Reward,Hero | HeroLevel | HeroLevel→ShopGroup(0.7) | DECODED |
| racereward | 100 | Reward | SectionID | SectionID→Section(1.0); TimeGift→Gift(1.0) | DECODED |
| sendgiftcontrol | 39 | Reward,Friend | HeroID | FavoriteGoodID→Item(1.0); HeroID→Unit(1.0) | DECODED |
| collectmiracle | 339 | Roguelite | MiracleID | MiracleID→Item(1.0) | DECODED |
| randomevent | 384 | Roguelite | EventID | EventValue→ShopGroup(0.923); NPCID→Unit(0.905) | DECODED |
| reliccollect | 66 | Roguelite |  | BlessID→ShopGroup(1.0); NameID→LanguageKey(1.0) | DECODED |
| relicevent | 292 | Roguelite | EventID | RelicList→Item(0.968); RelicListExpert→Item(0.953) | DECODED |
| relicrecommend | 41 | Roguelite |  | DescID→LanguageKey(1.0); NameID→LanguageKey(1.0) | DECODED |
| appearanceshop | 47 | Shop,Inventory | GoodsID | ItemID→Item(1.0); ItemPrice→ShopGroup(0.571) | DECODED |
| mazeshop | 127 | Shop | ID | FloorInterval→ShopGroup(1.0); ID→ShopGroup(0.717) | DECODED |
| recharge | 254 | Shop | RechargeID,RechargeNameID | RechargeArea→ShopGroup(0.5); RechargeLevel→ShopGroup(0.669) | DECODED |
| rechargeaccumulate | 12 | Shop | AccRechargNum,AccRechargeID | AccRechargeID→MonsterEventTable(1.0); AccRechargeLevel→ShopGroup(1.0) | DECODED |
| rechargeage | 3 | Shop |  | — | DECODED |
| shopconfig | 25 | Shop | ShopID | GoodsGroupId→ShopGroup(1.0); RefreshInterval→ShopGroup(0.714) | DECODED |
| shopgoodsgroup | 1567 | Shop | GoodsID | GoodsID→Goods(1.0); GroupID→ShopGroup(1.0) | DECODED |
| tradeactivity | 87 | Shop,Activity | TradeID | TradeDist→Gift(1.0); TradeLimitNum→ShopGroup(0.8) | DECODED |
| vip | 15 | Shop |  | — | PARSED_NO_SCHEMA |
| actionenum | 133 | System | EffectID | ParamNum→ShopGroup(1.0) | DECODED |
| componentbase | 1895 | System | ID | DoorStopID→Unit(0.679); EventDifficulty→ShopGroup(0.875) | DECODED |
| condtionenum | 30 | System | CondtionID | ParamNum→ShopGroup(1.0) | DECODED |
| director | 109 | System | DirectorId | — | DECODED |
| directortimeline | 682 | System | ID | ID→ShopGroup(0.55); InstanceId→ShopGroup(0.909) | DECODED |
| elementsynthesis | 64 | System | ElementSynthesisID,ItemID | ComposeNumLimit→ShopGroup(0.714); ComposeOrde→Item(1.0) | DECODED |
| eventtable | 43 | System |  | — | PARSED_NO_SCHEMA |
| expressionanim | 41 | System | ExpressionID | ExpressionID→LanguageKey(0.878) | DECODED |
| expressionanimstatus | 1534 | System | InteractiveID | AnimID→LanguageKey(1.0); BubbleTalk→LanguageKey(1.0) | DECODED |
| expressioninteractivearea | 124 | System | AppearanceID | AppearanceID→Item(0.919); Live2dEyeArea→ShopGroup(0.5) | DECODED |
| formation | 562 | System | FormationID | — | DECODED |
| functionenum | 38 | System | EffectID | ParamNum→ShopGroup(1.0) | DECODED |
| globalparamstring | None | System |  | — | ERROR |
| gmadvanceaccount | None | System |  | — | ERROR |
| language | 28996 | System |  | Key→LanguageKey(1.0) | DECODED |
| languagefavor | 10081 | System | Key | — | DECODED |
| languagetalk | 17894 | System | Key | — | DECODED |
| languageui | 6277 | System | Key | — | DECODED |
| spineanimation | 42 | System | HeroID | HeroID→Unit(1.0) | DECODED |
| systemsound | 2012 | System | SoundID | — | DECODED |
| activitytask | 314 | Task,Activity | ChallengeTaskID | GiftGroup→Gift(1.0); TaskConditionID→TaskCondition(1.0) | DECODED |
| activitytaskbox | 55 | Task,Activity | BoxID | ActivityParam1→ShopGroup(0.7); BoxID→ShopGroup(0.636) | DECODED |
| challengelimitedtask | 174 | Task,Challenge | ChallengeTaskID,TaskConditionID | ChallengeTaskID→TaskCondition(0.954); GiftGroup→Gift(1.0) | DECODED |
| challengetask | 60 | Task,Challenge | ChallengeTaskID,GiftGroup | GiftGroup→Gift(1.0); TaskConditionID→TaskCondition(1.0) | DECODED |
| dailytask | 40 | Task | DailyTaskID,GiftGroup | AcceptLevel→ShopGroup(0.909); DailyTaskID→DailyTask(1.0) | DECODED |
| favorabilitydailytask | 351 | Task,Friend | CompleteDescribe,TargetDescribe | CompleteDescribe→LanguageKey(1.0); HeroID→Unit(1.0) | DECODED |
| favorabilityspecialtask | 4 | Task,Friend | HeroID,TargetDescribe | HeroID→Unit(1.0); TargetDescribe→LanguageKey(1.0) | DECODED |
| holidaytask | 1 | Task,Activity |  | — | PARSED_NO_SCHEMA |
| moontaskdisplay | 10 | Task,Activity | Difficulty,Language | Difficulty→ShopGroup(1.0); Language→LanguageKey(1.0) | DECODED |
| moontaskrank | 10 | Task,Activity | Level | Difficulty→ShopGroup(1.0); DifficultyPower→ShopGroup(0.5) | DECODED |
| newyearcooktask | 50 | Task,Activity | ChallengeTaskID,TaskConditionID | GiftGroup→Gift(1.0); TaskConditionID→TaskCondition(1.0) | DECODED |
| newyearfoodtask | 78 | Task,Activity | ChallengeTaskID,TaskConditionID | GiftGroup→Gift(1.0); TaskConditionID→TaskCondition(1.0) | DECODED |
| returntask | 40 | Task,Activity | DailyTaskID,GiftGroup | GiftGroup→Gift(1.0); TaskConditionID→TaskCondition(1.0) | DECODED |
| taskcondition | 1728 | Task | TaskConditionID | CompleteNum→ShopGroup(0.411); CompleteValue1→Section(0.559) | DECODED |
| taskconditionline | 139 | Task | AchievementConditionID | CompleteNum→ShopGroup(0.415); CompleteValue1→Unit(0.533) | DECODED |
| taskcontrol | 1 | Task |  | ActivityActiveValueNumber→ShopGroup(0.8); ActivityGiftGroup→Gift(1.0) | DECODED |
| taskhappy | 42 | Task | GiftGroup,TaskConditionID | GiftGroup→Gift(1.0); TaskConditionID→TaskCondition(1.0) | DECODED |
| taskseven | 75 | Task | TaskConditionID,TaskDescribe | GiftGroup→Gift(1.0); TaskConditionID→TaskCondition(1.0) | DECODED |
| tower | 24 | Tower | ID,TowerItem | CostNumber→ShopGroup(0.7); ID→ShopGroup(1.0) | DECODED |
| towerbase | 50 | Tower | TowerID,TowerUnitID | LevelUpCost→Tower(0.444); TowerCost→ShopGroup(0.5) | DECODED |
| towercontroller | 23 | Tower | ID | EffectList→ShopGroup(1.0); Gold→Tower(0.583) | DECODED |
| towergrid | 16 | Tower | GirdID | GirdID→ShopGroup(1.0); GirdNumberGroup→ShopGroup(0.57) | DECODED |
| towerrank | 24 | Tower | ID,Rank | ID→Section(1.0); Rank→ShopGroup(1.0) | DECODED |
| worldbossevent | 75 | WorldBoss | EventID | Answer1→LanguageKey(1.0); Answer2→LanguageKey(1.0) | DECODED |
| worldbossexplore | 4 | WorldBoss | EventDesc,EventName | EventDesc→LanguageKey(1.0); EventName→LanguageKey(1.0) | DECODED |
| worldbossinfo | 10 | WorldBoss | BossID,StageID | AwardPreview01→Item(1.0); AwardPreview02→Item(1.0) | DECODED |
