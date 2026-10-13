; BattlePassModule$$GetBattlePassMainPrefab
; RVA [0x1858d9c,0x1858e80), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 61bd31cba89149f19d917635cf60fd70a09eae273c95e6c71a78aeab09aedd87
001858d9c: stp      x20, x19, [sp, #-0x20]! ;
001858da0: stp      x29, x30, [sp, #0x10] ;
001858da4: add      x29, sp, #0x10 ;
001858da8: adrp     x19, #0x5577000 ;
001858dac: ldrb     w8, [x19, #0x66a] ;
001858db0: tbnz     w8, #0, #0x1858dcc ;
001858db4: adrp     x8, #0x523c000 ;
001858db8: ldr      x8, [x8, #0x1a0] ;
001858dbc: ldr      w0, [x8] ;
001858dc0: bl       #0x3f2aed0 ;
001858dc4: mov      w8, #1 ;
001858dc8: strb     w8, [x19, #0x66a] ;
001858dcc: adrp     x8, #0x51ed000 ;
001858dd0: ldr      x8, [x8, #0xb60] ;
001858dd4: ldr      x0, [x8] ;
001858dd8: ldrb     w8, [x0, #0x10a] ;
001858ddc: tbz      w8, #0, #0x1858dec ;
001858de0: ldr      w8, [x0, #0xbc] ;
001858de4: cbnz     w8, #0x1858dec ;
001858de8: bl       #0x3f3f378 ;
001858dec: adrp     x8, #0x51d9000 ;
001858df0: ldr      x8, [x8, #0x618] ;
001858df4: mov      x0, xzr ;
001858df8: ldr      x1, [x8] ;
001858dfc: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
001858e00: mov      x19, x0 ;
001858e04: cbnz     x19, #0x1858e0c ;
001858e08: bl       #0x3f564f0 ;
001858e0c: adrp     x8, #0x5252000 ;
001858e10: ldr      x8, [x8, #0xae0] ;
001858e14: mov      x0, x19 ;
001858e18: ldr      x1, [x8] ;
001858e1c: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
001858e20: cbz      x0, #0x1858e68 ;
001858e24: mov      x2, xzr ;
001858e28: mov      w1, #0x38 ;
001858e2c: bl       #0x132e22c ; ActivityNoticeModule$$GetActivityData
001858e30: adrp     x19, #0x5287000 ;
001858e34: ldr      x19, [x19, #0xda0] ;  STRING_REF='UI_BattlePass_Main'
001858e38: cbz      x0, #0x1858e70 ;
001858e3c: mov      x1, xzr ;
001858e40: bl       #0x1324668 ; ActivityInfo$$get_ActivityGroup
001858e44: adrp     x8, #0x528a000 ;
001858e48: ldr      x8, [x8, #0x798] ;  STRING_REF='UI_BattlePass_Main2'
001858e4c: adrp     x9, #0x5202000 ;
001858e50: ldr      x9, [x9, #0xd60] ;  STRING_REF='UI_BattlePass_Main3'
001858e54: cmp      w0, #0x17 ;
001858e58: csel     x8, x8, x19, eq ;
001858e5c: cmp      w0, #0x22 ;
001858e60: csel     x19, x9, x8, eq ;
001858e64: b        #0x1858e70 ;
001858e68: adrp     x19, #0x5287000 ;
001858e6c: ldr      x19, [x19, #0xda0] ;  STRING_REF='UI_BattlePass_Main'
001858e70: ldr      x0, [x19] ;
001858e74: ldp      x29, x30, [sp, #0x10] ;
001858e78: ldp      x20, x19, [sp], #0x20 ;
001858e7c: ret       ;
