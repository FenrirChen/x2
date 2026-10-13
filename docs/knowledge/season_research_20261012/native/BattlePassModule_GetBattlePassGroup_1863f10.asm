; BattlePassModule$$GetBattlePassGroup
; RVA [0x1863f10,0x1864000), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 3c807aebe68a7938178de2b78ec5476423506085dac0a89e933a1b66adcad06a
001863f10: stp      x20, x19, [sp, #-0x20]! ;
001863f14: stp      x29, x30, [sp, #0x10] ;
001863f18: add      x29, sp, #0x10 ;
001863f1c: adrp     x19, #0x5577000 ;
001863f20: ldrb     w8, [x19, #0x6c9] ;
001863f24: tbnz     w8, #0, #0x1863f40 ;
001863f28: adrp     x8, #0x5304000 ;
001863f2c: ldr      x8, [x8, #0x708] ;
001863f30: ldr      w0, [x8] ;
001863f34: bl       #0x3f2aed0 ;
001863f38: mov      w8, #1 ;
001863f3c: strb     w8, [x19, #0x6c9] ;
001863f40: adrp     x8, #0x51ed000 ;
001863f44: ldr      x8, [x8, #0xb60] ;
001863f48: ldr      x0, [x8] ;
001863f4c: ldrb     w8, [x0, #0x10a] ;
001863f50: tbz      w8, #0, #0x1863f60 ;
001863f54: ldr      w8, [x0, #0xbc] ;
001863f58: cbnz     w8, #0x1863f60 ;
001863f5c: bl       #0x3f3f378 ;
001863f60: adrp     x8, #0x51d9000 ;
001863f64: ldr      x8, [x8, #0x618] ;
001863f68: mov      x0, xzr ;
001863f6c: ldr      x1, [x8] ;
001863f70: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
001863f74: mov      x19, x0 ;
001863f78: cbnz     x19, #0x1863f80 ;
001863f7c: bl       #0x3f564f0 ;
001863f80: adrp     x8, #0x5252000 ;
001863f84: ldr      x8, [x8, #0xae0] ;
001863f88: mov      x0, x19 ;
001863f8c: ldr      x1, [x8] ;
001863f90: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
001863f94: mov      x19, x0 ;
001863f98: cbnz     x19, #0x1863fa0 ;
001863f9c: bl       #0x3f564f0 ;
001863fa0: mov      x2, xzr ;
001863fa4: mov      w1, #0x37 ;
001863fa8: mov      x0, x19 ;
001863fac: bl       #0x132e22c ; ActivityNoticeModule$$GetActivityData
001863fb0: cbz      x0, #0x1863fcc ;
001863fb4: mov      x1, xzr ;
001863fb8: bl       #0x1324668 ; ActivityInfo$$get_ActivityGroup
001863fbc: cmp      w0, #0x10 ;
001863fc0: b.ne     #0x1863fd4 ;
001863fc4: mov      w0, #1 ;
001863fc8: b        #0x1863ff4 ;
001863fcc: mov      w0, wzr ;
001863fd0: b        #0x1863ff4 ;
001863fd4: cmp      w0, #0x17 ;
001863fd8: b.ne     #0x1863fe4 ;
001863fdc: mov      w0, #2 ;
001863fe0: b        #0x1863ff4 ;
001863fe4: cmp      w0, #0x22 ;
001863fe8: mov      w8, #1 ;
001863fec: mov      w9, #3 ;
001863ff0: csel     w0, w9, w8, eq ;
001863ff4: ldp      x29, x30, [sp, #0x10] ;
001863ff8: ldp      x20, x19, [sp], #0x20 ;
001863ffc: ret       ;
