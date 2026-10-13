"""Reuse the audited ELF decoder, selecting only season-related consumer methods."""
from pathlib import Path
source=Path('D:/demo/x2/moni/data/evidence/audit_followup_20261012/build_evidence.py').read_text('utf8')
source=source.split('cat = json.loads',1)[0]
start=source.index('targets = {');end=source.index('\nmd = ',start)
targets={
 'BattlePassModule$$InitData','BattlePassModule$$Show','BattlePassModule$$CheckSeasonOpen',
 'BattlePassModule$$OnHandleActivitySync','BattlePassModule$$GetBattlePassGroup',
 'BattlePassModule$$IsBattlePassEnd','BattlePassModule$$CheckBattlePassCanBuy',
 'BattlePassModule$$QueryBattlePassMissionData','BattlePassModule$$CheckFirstChallenge',
 'BattlePassModule$$CheckBattlePassChapterOpen','BattlePassModule$$CheckBattlePassChallengeOpen',
 'BattlePassModule$$InitChallengeSection','BattlePassModule$$GetSelectBattlePassChallengeId',
 'BattlePassModule$$InitRelic','BattlePassModule$$DoArtifactOpt',
 'BattlePassModule$$GetTalentGroupList','ClientSeasonProperty$$RefreshBaseProperty',
 'ClientSeasonProperty$$RefreshEquip','ClientSeasonProperty$$RefreshGodEquip',
 'BattlePassAchievementModule$$InitData',
 'BattlePassModule$$GetBattlePassMainPrefab','BattlePassModule$$GetBattlePassChapterPrefab',
 'BattlePassModule$$GetBattlePassFarmPrefab'}
source=source[:start]+'targets = '+repr(targets)+source[end:]
source+='\nprint("Season native methods",len(method_index))\n'
exec(compile(source,'<audited-ELF-decoder>','exec'),globals())
