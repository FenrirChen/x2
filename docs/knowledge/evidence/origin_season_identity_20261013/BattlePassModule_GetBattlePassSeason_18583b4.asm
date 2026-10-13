; BattlePassModule$$GetBattlePassSeason
; RVA [0x18583b4,0x18583e8), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 29bcfcff6f659a458e13050c1a88e9b85b8918e6ed416a9d0a63434bfbeebe59
0018583b4: cmp      w1, #0x10 ;
0018583b8: b.ne     #0x18583c4 ;
0018583bc: mov      w0, #1 ;
0018583c0: ret       ;
0018583c4: cmp      w1, #0x17 ;
0018583c8: b.ne     #0x18583d4 ;
0018583cc: mov      w0, #2 ;
0018583d0: ret       ;
0018583d4: cmp      w1, #0x22 ;
0018583d8: mov      w8, #1 ;
0018583dc: mov      w9, #3 ;
0018583e0: csel     w0, w9, w8, eq ;
0018583e4: ret       ;
