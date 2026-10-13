; BattlePassModule$$GetBattlePassFarmPrefab
; RVA [0x1858e80,0x1858f38), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 5c1d189d4591a9adadad1b42af161f1686b9eecf4eef64ef7303b48b01f1a9f0
001858e80: stp      x20, x19, [sp, #-0x20]! ;
001858e84: stp      x29, x30, [sp, #0x10] ;
001858e88: add      x29, sp, #0x10 ;
001858e8c: adrp     x19, #0x5577000 ;
001858e90: ldrb     w8, [x19, #0x66b] ;
001858e94: tbnz     w8, #0, #0x1858eb0 ;
001858e98: adrp     x8, #0x5226000 ;
001858e9c: ldr      x8, [x8, #0x1f8] ;
001858ea0: ldr      w0, [x8] ;
001858ea4: bl       #0x3f2aed0 ;
001858ea8: mov      w8, #1 ;
001858eac: strb     w8, [x19, #0x66b] ;
001858eb0: adrp     x8, #0x51ed000 ;
001858eb4: ldr      x8, [x8, #0xb60] ;
001858eb8: ldr      x0, [x8] ;
001858ebc: ldrb     w8, [x0, #0x10a] ;
001858ec0: tbz      w8, #0, #0x1858ed0 ;
001858ec4: ldr      w8, [x0, #0xbc] ;
001858ec8: cbnz     w8, #0x1858ed0 ;
001858ecc: bl       #0x3f3f378 ;
001858ed0: adrp     x8, #0x51d9000 ;
001858ed4: ldr      x8, [x8, #0x618] ;
001858ed8: mov      x0, xzr ;
001858edc: ldr      x1, [x8] ;
001858ee0: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
001858ee4: mov      x19, x0 ;
001858ee8: cbnz     x19, #0x1858ef0 ;
001858eec: bl       #0x3f564f0 ;
001858ef0: adrp     x8, #0x5252000 ;
001858ef4: ldr      x8, [x8, #0xae0] ;
001858ef8: mov      x0, x19 ;
001858efc: ldr      x1, [x8] ;
001858f00: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
001858f04: cbz      x0, #0x1858f20 ;
001858f08: mov      x2, xzr ;
001858f0c: mov      w1, #0x37 ;
001858f10: bl       #0x132e22c ; ActivityNoticeModule$$GetActivityData
001858f14: cbz      x0, #0x1858f20 ;
001858f18: mov      x1, xzr ;
001858f1c: bl       #0x1324668 ; ActivityInfo$$get_ActivityGroup
001858f20: adrp     x8, #0x52d1000 ;
001858f24: ldr      x8, [x8, #0x7f8] ;  STRING_REF='UI_BattlePass_Farm'
001858f28: ldr      x0, [x8] ;
001858f2c: ldp      x29, x30, [sp, #0x10] ;
001858f30: ldp      x20, x19, [sp], #0x20 ;
001858f34: ret       ;
