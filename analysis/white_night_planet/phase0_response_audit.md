# College Phase 0 response audit (2026-09-27)

Evidence: official 2.4 `dump.cs`, `script.json`, and ARM64 `libil2cpp.so` under `D:/demo/x2/`. Offsets below are native object offsets, not protobuf tag numbers. Direct native reads are distinguished from declared fields. No original server response or live College request sequence was available during this audit.

## 584 `L2C_QueryGrowthBase`

`CollegeModule.OnGetQueryGrowthBaseData` 0x1AF8850 checks the runtime message type, stores the entire object at `CollegeModule+0x68` (0x1AF88D4), directly reads `washingCountDay` at response +0x60 into module +0x168, calls `CollegeInit` once (0x1AF88EC), and fires event 0x101 (0x1AF8928). **There is no `code` field or result comparison in this message.** The 13 declared fields are a cached authoritative object, not 13 proven direct reads in this handler. `CollegeInit` starts power and energy timers (0x1AF61F0/0x1AF61F8), so an incomplete snapshot can fail downstream even though 584 itself accepts it. The exact UI field read set and the minimum non-null list/queue set remain UNKNOWN; declaring every field required would overstate evidence. The current `exploreList=[empty message]`, `trainingList=[empty message]`, and `prayQueue=[empty message]` are fabricated entries and should not be treated as an official empty state.

## 591 `L2C_AlchemyMainData`

`CollegeAlchemyModule.OnReceiveAlchemyMainDataMsg` 0x189CC90 compares `code` at +0x10 to 10. On success it reads `recipeIdExp` +0x18, `customeres` +0x20, `productionBars` +0x28, `elements` +0x30, `buffType` +0x38, and `buffCount` +0x3C. It clears local recipe maps, loops the lists, resets five local customer/production positions and six elemental positions, calls `RefreshAlchemyBadge`, then fires event 0x16. Empty *constructed lists* have zero iterations; a null list is unsafe because `get_Count` is invoked without an explicit null fallback. There are no separate level, timer, unlock flag, or pending reward fields in this message. `CollegeMainEntry.OnOpen` sends 590 unconditionally (0x1AF4024), after 622; its handler fires an event on success but `OnOpen` does not await it. Thus 591 is a main-entry refresh dependency, while a strict navigation blocking dependency remains unproven without an entry/UI trace.

## 623 `L2C_UnlockExploreRuin`

`CollegeModule.SendUnlockExploreRuin` 0x1AF40E4 constructs an empty request. `OnReceiveUnlockExploreRuin` 0x1AFE168 tests `code` +0x10 for 10. On success, a non-null `unlockExploreRuin` list at +0x18 replaces the module's list at +0x120 (0x1AFE268–274); a null list leaves the previous list and logs an error. A non-10 code reaches `GameAPI.ShowErrorCodeBubble` (0x1AFE214–244), so fixed code 13 is visible to the player. The request has no ruin ID or cost; the direct consumer performs no mutation. The wire behaves as a query/ensure-state request from this entry path. Official server-side unlock conditions and whether an empty list is valid are UNKNOWN, so no resource deduction or synthetic unlock should be inferred. Repeating the same request should return the same current state.

## Pushes

| ID | Native finding | Phase 1 requirement |
|---|---|---|
| 559 BuildingUpdate | Type declared (`type` +0x10, `buildingList` +0x18); no named College handler located in `script.json`. Registration and actual consumer UNKNOWN. | No new push without a proven mutation. |
| 561 ExploreUpdate | Type declared; no named College handler located. Registration and actual consumer UNKNOWN. | No new push. |
| 562 TrainingUpdate | `CollegeModule.OnReceiveTrainingUpdateMsg` 0x1AFB648 reads its list at +0x10, matches entry IDs against `growthData.trainingList` at +0x38 and replaces matches. It dereferences `growthData`; no snapshot means unsafe. Registration must still be independently confirmed. | Only when training mutations exist; a fresh 579 can supply full state. |
| 617 QueryGrowthBaseAlchemy | Type declared (`code`, `elements`, `starEnergy`, `starGainTime`, `buffType`, `buffCount`); no named College handler located. Registration/consumer UNKNOWN. | Do not emit. |

## Reward replies (no business implementation in Phase 1)

| Reply | Handler RVA | Confirmed direct reads | Remaining audit |
|---|---|---|---|
| 250 FinishExplore | 0x1AFD670 | `code` +0x10, `rewardData` +0x18, `ruinId` +0x20, `exp` +0x24 | `exploreId` downstream effects and item push sequence UNKNOWN. |
| 603 AlchemyCollect | 0x189F4C4 | `code` +0x10, `recipeId` +0x20, `posIndex` +0x28 | `rewardData` handoff and item push sequence UNKNOWN. |
| 599 AlchemyFinish | 0x189EBD8 | `rewardData` +0x20, `posIndex` +0x18, `alchemyType` +0x28 observed | Full success branch/item push sequence UNKNOWN. |
| 827 AlchemyOnekeyCollect | 0x18A0DCC | `code` +0x10, `barData` +0x20 observed | `rewardData` handoff/item push sequence UNKNOWN. |
| 372 BuildRewardPrayGod | 0x1DB7190 | `code` +0x10 and `rewardData` +0x18 observed | Item push sequence UNKNOWN. |

## Startup order

`CollegeEntry.OnOpen` 0x1BAFF2C conditionally sends 579. `CollegeMainEntry.OnOpen` 0x1AF3EFC directly sends 622 at 0x1AF3FA4, then 590 at 0x1AF4024. A MainHallFSM branch also sends 590 under function-open checks. This proves local call order for the main entry, **not** network receive order among 579/622/590. Live client telemetry remains unobserved.

## Remaining UNKNOWN and implementation gate

The nested GrowthBase UI consumers, valid initial ruin list, initial alchemy list semantics, wonder 728 unlock condition, and push registration remain insufficiently closed. Phase 1 can safely provide a persistent snapshot source for 584/Login and an idempotent 623 query of stored state. Declaring the *full* base entry complete, or returning `code=10` with guessed empty alchemy/ruin lists, would be unsupported until those states are proven or explicitly adopted as Revival compatibility rules.
