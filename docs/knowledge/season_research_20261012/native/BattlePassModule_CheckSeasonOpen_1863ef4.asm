; BattlePassModule$$CheckSeasonOpen
; RVA [0x1863ef4,0x1863f10), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 94aa554ce8cf24d76194241f8d8b6dd5a9e3b83ed3754af88fd5993a851db463
001863ef4: ldr      w8, [x0, #0x14] ;
001863ef8: cmp      w8, w1 ;
001863efc: cset     w9, eq ;
001863f00: cmp      w8, #0 ;
001863f04: cset     w8, ne ;
001863f08: and      w0, w9, w8 ;
001863f0c: ret       ;
