---
Document-Type: Current Knowledge
Domain: Tutorial Onboarding
Status: PARTIAL / DEVICE VALIDATION REQUIRED
Updated: 2026-09-28
Evidence: phase5_output/business/first_tutorial_chain.json; phase5_output/business/guide_persistence.json; Il2CppDumper dump.cs
---

# 新号教程与首次命名

## Original client flow established so far

`L2C_Login.isCreateRole` marks first login. `ChapterModule.StartTitoGuideBattle`
(RVA `0x16BDC2C`) selects Chapter `2010000`, Section `2110001`, Hero `1003`.
The first active guide row after that battle is Guide `21011`/Group `1`, followed
by `21012`, `21021`–`21023`, and the Chapter 1 group `21031`–`21033`.
`NamePlayerWindow` has an input and confirm button (`OnBtnConfirmClick`
RVA `0x174830C`); `AccountInfoModule.ModifyPlayerName` is at `0x13108DC`.
The native `AccountOpt` names first naming as `AO_PLAYER_NICKNAME_ONCREATE=7`.

The *specific* story-end callback and the visual `GameStartLoadingPage` progress
condition remain unproven. Dump metadata identifies
`GameStartLoadingPage.OnUpdate` RVA `0x1388F10` and `OnFadeOut` RVA `0x1389694`,
but provides signatures, not method bodies. The real 16:10:29 trace in
`runtime/phase14/mail_fix_20260928.err.log` records player 2 requesting
`C2L_FightData(126)` for section 2110001/chapter 2010000/scene 2210001,
followed by `L2C_FightData(130) result=13`. Their persisted `heroes=[]` makes
the existing entry validation necessarily reject any selected hero. The native
consumer is `ChapterModule.OnL2CFightDataReceiveMsg` RVA `0x16C0468`, with
request method `SendBattleRequest` RVA `0x16BDCF0`. The native callgraph
shows `StartTitoGuideBattle → SendBattleRequest` and the response consumer
calling `AppMainImpl.StartBattle` on its successful path. This failed entry is the
concrete server-side blocker after the story. The exact screen progress formula
and readiness branches still require native method body or device evidence.

## New player initial state (Revival compatibility)

Registration creates one snapshot with `bootstrap_version=1`,
`tutorial_mode=tutorial`, empty nickname, and Hero 1003 (level 1/star 1)
in `heroAll`; the latter is required by the forced battle and Guide 21022.
Initial currency remains zero and stamina 60. The exact original grant rule
for Hero 1003 is lost. Login increments count without reinitializing the
snapshot; subsequent login reports `isCreateRole=false`.

## Guide, mission, and naming protocol

| Action | C2L ID | Server | L2C | Status |
|---|---:|---|---|---|
| Step state | GuideStep 374 | TutorialService, snapshot `guide_steps` | GuideStep 375 code 10 | Implemented; device pending |
| Group completion | Account 141 opt 3, values `[group,next]` | AppearanceService, snapshot `guide_groups` | Account 142 result 10 + PlayerData QuestIDs | Implemented; device pending |
| Tutorial mission prepare | PrepareMainMission 151 | BattleService, static Chapter/Section check | PrepareMainMission 153 | Implemented; device pending |
| Fight entry | FightData 126 | BattleService; requires owned Hero 1003 | FightData 130 result 10 + data/profile | Previously rejected 13; isolated test passes; device pending |
| First name | Account 141 opt 7, `strvals=[name]` | AppearanceService | Account 142 result 10 + PlayerData NickName | Implemented; device pending |

`TitoGuideModule.SendGuideFinish` (RVA `0x15AF1B4`) invokes
`AccountInfoModule.FinishTitoGuide` (RVA `0x130F11C`) and sends opt 3.
`BaseInfoProto.QuestIDs` is a repeated int/int pair at field 15; its snapshot
source is `guide_groups`. Step messages are supplementary, not the only guide
persistence. First naming permits 1–16 printable characters, rejects whitespace
only and control input, charges nothing, and accepts a repeated identical
request. The precise original maximum length and uniqueness policy remain
unknown; these validation limits are Revival compatibility.

## Old skip and early accounts

`OLD_TUTORIAL_SKIP_BEHAVIOR`: No current explicit skip flag or GuideStep
advance was found in the server. The registration snapshot in
`src/x2server/player/new_player.py` gave every new account `nickname=Revival`,
`heroes=[]`, and no main or guide state; trigger was every `/register` call.
`PlayerStore.save_snapshot` rejected empty nicknames. Account opt 3/7 returned
result 13 and GuideStep 374 was unhandled. These are concrete new-account
inconsistencies even though the precise 99% wait is unconfirmed.

`X2_SKIP_TUTORIAL=true` now explicitly retains the former minimal development
snapshot. Default is tutorial mode. No existing legacy player is migrated on
login. `tools/repair_early_tutorial_account.py` defaults to a read-only preview
and repairs one explicitly identified account only when its snapshot still
matches the untouched early-registration pattern. Player 2 (`fenrir`) is
eligible on dry run; the active DB has not been modified.

## Known unknowns and validation gate

The exact story-to-loading callback, the visual condition at 99%, whether naming
occurs before or after the first battle, and later tutorial rewards/materials
still need native method body analysis and a fresh device trace. The existing
server telemetry now records unknown ID, player ID, payload length, and handler
status without body dumps or credentials. Fresh registration through naming,
post-name progression, and relog must pass on device before deployment.

User reported the fresh-account device test completed without problems after
the 18:40 restart. No further 99% or naming issue was reported. The precise
Loading UI progress formula remains a static-analysis unknown.

At 18:40 local time the repaired local server reported ready on HTTP 18080,
game TCP 29000, and chat TCP 29001. Its trace is
`runtime/phase14/tutorial_20260928.err.log`. The active database remains
unchanged for players 1 and 2; no repair was applied.
