; BattlePassModule$$InitRelic
; RVA [0x185c7a0,0x185c8a4), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 d9bad8b5d76929a1357e3c85e9cd79948daebb1467160c20f0aedea5a1f5fce1
00185c7a0: stp      x20, x19, [sp, #-0x20]! ;
00185c7a4: stp      x29, x30, [sp, #0x10] ;
00185c7a8: add      x29, sp, #0x10 ;
00185c7ac: adrp     x20, #0x5577000 ;
00185c7b0: ldrb     w8, [x20, #0x6bc] ;
00185c7b4: mov      x19, x0 ;
00185c7b8: tbnz     w8, #0, #0x185c7d4 ;
00185c7bc: adrp     x8, #0x52eb000 ;
00185c7c0: ldr      x8, [x8, #0x128] ;
00185c7c4: ldr      w0, [x8] ;
00185c7c8: bl       #0x3f2aed0 ;
00185c7cc: mov      w8, #1 ;
00185c7d0: strb     w8, [x20, #0x6bc] ;
00185c7d4: adrp     x8, #0x51ed000 ;
00185c7d8: ldr      x8, [x8, #0xb60] ;
00185c7dc: ldr      x0, [x8] ;
00185c7e0: ldrb     w8, [x0, #0x10a] ;
00185c7e4: tbz      w8, #0, #0x185c7f4 ;
00185c7e8: ldr      w8, [x0, #0xbc] ;
00185c7ec: cbnz     w8, #0x185c7f4 ;
00185c7f0: bl       #0x3f3f378 ;
00185c7f4: adrp     x8, #0x51d9000 ;
00185c7f8: ldr      x8, [x8, #0x618] ;
00185c7fc: mov      x0, xzr ;
00185c800: ldr      x1, [x8] ;
00185c804: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
00185c808: mov      x20, x0 ;
00185c80c: cbnz     x20, #0x185c814 ;
00185c810: bl       #0x3f564f0 ;
00185c814: adrp     x8, #0x5252000 ;
00185c818: ldr      x8, [x8, #0xae0] ;
00185c81c: mov      x0, x20 ;
00185c820: ldr      x1, [x8] ;
00185c824: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
00185c828: mov      x20, x0 ;
00185c82c: cbnz     x20, #0x185c834 ;
00185c830: bl       #0x3f564f0 ;
00185c834: mov      w2, wzr ;
00185c838: mov      x3, xzr ;
00185c83c: mov      w1, #0x37 ;
00185c840: mov      x0, x20 ;
00185c844: bl       #0x1317cf4 ; ActivityNoticeModule$$CheckActivityOpen
00185c848: tbz      w0, #0, #0x185c898 ;
00185c84c: adrp     x8, #0x5270000 ;
00185c850: ldr      x8, [x8, #0x340] ;
00185c854: ldr      x0, [x8] ;
00185c858: ldrb     w8, [x0, #0x10a] ;
00185c85c: tbz      w8, #0, #0x185c86c ;
00185c860: ldr      w8, [x0, #0xbc] ;
00185c864: cbnz     w8, #0x185c86c ;
00185c868: bl       #0x3f3f378 ;
00185c86c: bl       #0x1856624 ; BattlepassMiracleManager$$get_Instance
00185c870: ldr      w20, [x19, #0x14] ;
00185c874: cbnz     x0, #0x185c87c ;
00185c878: bl       #0x3f564f0 ;
00185c87c: mov      w1, w20 ;
00185c880: bl       #0x18568f4 ; BattlepassMiracleManager$$GetItem
00185c884: str      x0, [x19, #0x178] ;
00185c888: ldp      x29, x30, [sp, #0x10] ;
00185c88c: mov      x0, x19 ;
00185c890: ldp      x20, x19, [sp], #0x20 ;
00185c894: b        #0x1862ee4 ; BattlePassModule$$QuerySeasonRelic
00185c898: ldp      x29, x30, [sp, #0x10] ;
00185c89c: ldp      x20, x19, [sp], #0x20 ;
00185c8a0: ret       ;
