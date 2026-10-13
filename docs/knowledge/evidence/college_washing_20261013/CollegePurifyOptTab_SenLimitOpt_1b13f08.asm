; CollegePurifyOptTab$$SenLimitOpt
; RVA [0x1b13f08,0x1b1406c), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 e10b8ccecc1e96f46ff900309a496f1e26ce4c5726a22fd300103fdd7b65a480
001b13f08: stp      x22, x21, [sp, #-0x30]! ;
001b13f0c: stp      x20, x19, [sp, #0x10] ;
001b13f10: stp      x29, x30, [sp, #0x20] ;
001b13f14: add      x29, sp, #0x20 ;
001b13f18: sub      sp, sp, #0x10 ;
001b13f1c: adrp     x20, #0x5578000 ;
001b13f20: ldrb     w8, [x20, #0x8aa] ;
001b13f24: mov      x19, x0 ;
001b13f28: tbnz     w8, #0, #0x1b13f44 ;
001b13f2c: adrp     x8, #0x5301000 ;
001b13f30: ldr      x8, [x8, #0x458] ;
001b13f34: ldr      w0, [x8] ;
001b13f38: bl       #0x3f2aed0 ;
001b13f3c: mov      w8, #1 ;
001b13f40: strb     w8, [x20, #0x8aa] ;
001b13f44: ldr      w20, [x19, #0x17c] ;
001b13f48: cmp      w20, #1 ;
001b13f4c: b.lt     #0x1b13fe4 ;
001b13f50: adrp     x8, #0x51ed000 ;
001b13f54: adrp     x9, #0x5263000 ;
001b13f58: ldr      x8, [x8, #0x620] ;
001b13f5c: ldr      x9, [x9, #0x430] ;
001b13f60: ldr      x22, [x8] ;
001b13f64: ldr      x0, [x9] ;
001b13f68: bl       #0x3f6452c ;
001b13f6c: mov      x3, xzr ;
001b13f70: mov      x1, x19 ;
001b13f74: mov      x2, x22 ;
001b13f78: mov      x21, x0 ;
001b13f7c: bl       #0x3e63db4 ; System.Action$$.ctor
001b13f80: adrp     x8, #0x5243000 ;
001b13f84: ldr      x8, [x8, #0x7d0] ;
001b13f88: ldr      x0, [x8] ;
001b13f8c: ldrb     w8, [x0, #0x10a] ;
001b13f90: tbz      w8, #0, #0x1b13fa0 ;
001b13f94: ldr      w8, [x0, #0xbc] ;
001b13f98: cbnz     w8, #0x1b13fa0 ;
001b13f9c: bl       #0x3f3f378 ;
001b13fa0: adrp     x8, #0x525c000 ;
001b13fa4: ldr      x8, [x8, #0x120] ;  STRING_REF='UI_College_Building08'
001b13fa8: mov      x0, xzr ;
001b13fac: mov      x3, xzr ;
001b13fb0: mov      w5, wzr ;
001b13fb4: ldr      x6, [x8] ;
001b13fb8: mov      w4, #1 ;
001b13fbc: mov      w1, w20 ;
001b13fc0: mov      x2, x21 ;
001b13fc4: mov      w7, wzr ;
001b13fc8: str      xzr, [sp] ;
001b13fcc: bl       #0x1348078 ; UIAPI$$CostDiamond
001b13fd0: sub      sp, x29, #0x20 ;
001b13fd4: ldp      x29, x30, [sp, #0x20] ;
001b13fd8: ldp      x20, x19, [sp, #0x10] ;
001b13fdc: ldp      x22, x21, [sp], #0x30 ;
001b13fe0: ret       ;
001b13fe4: adrp     x8, #0x51ed000 ;
001b13fe8: ldr      x8, [x8, #0xb60] ;
001b13fec: ldr      x0, [x8] ;
001b13ff0: ldrb     w8, [x0, #0x10a] ;
001b13ff4: tbz      w8, #0, #0x1b14004 ;
001b13ff8: ldr      w8, [x0, #0xbc] ;
001b13ffc: cbnz     w8, #0x1b14004 ;
001b14000: bl       #0x3f3f378 ;
001b14004: adrp     x8, #0x51d9000 ;
001b14008: ldr      x8, [x8, #0x618] ;
001b1400c: mov      x0, xzr ;
001b14010: ldr      x1, [x8] ;
001b14014: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
001b14018: mov      x20, x0 ;
001b1401c: cbnz     x20, #0x1b14024 ;
001b14020: bl       #0x3f564f0 ;
001b14024: adrp     x8, #0x52ca000 ;
001b14028: ldr      x8, [x8, #0xf70] ;
001b1402c: mov      x0, x20 ;
001b14030: ldr      x1, [x8] ;
001b14034: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
001b14038: ldr      w19, [x19, #0x134] ;
001b1403c: mov      x20, x0 ;
001b14040: cbnz     x20, #0x1b14048 ;
001b14044: bl       #0x3f564f0 ;
001b14048: mov      x3, xzr ;
001b1404c: mov      w2, #4 ;
001b14050: mov      x0, x20 ;
001b14054: mov      w1, w19 ;
001b14058: sub      sp, x29, #0x20 ;
001b1405c: ldp      x29, x30, [sp, #0x20] ;
001b14060: ldp      x20, x19, [sp, #0x10] ;
001b14064: ldp      x22, x21, [sp], #0x30 ;
001b14068: b        #0x1b006fc ; CollegeModule$$SendWashingRoomOpt
