; CollegePurifyOptTab$$SendDeletOpt
; RVA [0x1b12f14,0x1b13078), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 1c1876c3eaf5658d41603f60a8abbb854ae1057ce570c7e8fa63a48623225875
001b12f14: stp      x22, x21, [sp, #-0x30]! ;
001b12f18: stp      x20, x19, [sp, #0x10] ;
001b12f1c: stp      x29, x30, [sp, #0x20] ;
001b12f20: add      x29, sp, #0x20 ;
001b12f24: sub      sp, sp, #0x10 ;
001b12f28: adrp     x20, #0x5578000 ;
001b12f2c: ldrb     w8, [x20, #0x8a4] ;
001b12f30: mov      x19, x0 ;
001b12f34: tbnz     w8, #0, #0x1b12f50 ;
001b12f38: adrp     x8, #0x51fc000 ;
001b12f3c: ldr      x8, [x8, #0xe60] ;
001b12f40: ldr      w0, [x8] ;
001b12f44: bl       #0x3f2aed0 ;
001b12f48: mov      w8, #1 ;
001b12f4c: strb     w8, [x20, #0x8a4] ;
001b12f50: ldr      w20, [x19, #0x17c] ;
001b12f54: cmp      w20, #1 ;
001b12f58: b.lt     #0x1b12ff0 ;
001b12f5c: adrp     x8, #0x5231000 ;
001b12f60: adrp     x9, #0x5263000 ;
001b12f64: ldr      x8, [x8, #0x5f8] ;
001b12f68: ldr      x9, [x9, #0x430] ;
001b12f6c: ldr      x22, [x8] ;
001b12f70: ldr      x0, [x9] ;
001b12f74: bl       #0x3f6452c ;
001b12f78: mov      x3, xzr ;
001b12f7c: mov      x1, x19 ;
001b12f80: mov      x2, x22 ;
001b12f84: mov      x21, x0 ;
001b12f88: bl       #0x3e63db4 ; System.Action$$.ctor
001b12f8c: adrp     x8, #0x5243000 ;
001b12f90: ldr      x8, [x8, #0x7d0] ;
001b12f94: ldr      x0, [x8] ;
001b12f98: ldrb     w8, [x0, #0x10a] ;
001b12f9c: tbz      w8, #0, #0x1b12fac ;
001b12fa0: ldr      w8, [x0, #0xbc] ;
001b12fa4: cbnz     w8, #0x1b12fac ;
001b12fa8: bl       #0x3f3f378 ;
001b12fac: adrp     x8, #0x525c000 ;
001b12fb0: ldr      x8, [x8, #0x120] ;  STRING_REF='UI_College_Building08'
001b12fb4: mov      x0, xzr ;
001b12fb8: mov      x3, xzr ;
001b12fbc: mov      w5, wzr ;
001b12fc0: ldr      x6, [x8] ;
001b12fc4: mov      w4, #1 ;
001b12fc8: mov      w1, w20 ;
001b12fcc: mov      x2, x21 ;
001b12fd0: mov      w7, wzr ;
001b12fd4: str      xzr, [sp] ;
001b12fd8: bl       #0x1348078 ; UIAPI$$CostDiamond
001b12fdc: sub      sp, x29, #0x20 ;
001b12fe0: ldp      x29, x30, [sp, #0x20] ;
001b12fe4: ldp      x20, x19, [sp, #0x10] ;
001b12fe8: ldp      x22, x21, [sp], #0x30 ;
001b12fec: ret       ;
001b12ff0: adrp     x8, #0x51ed000 ;
001b12ff4: ldr      x8, [x8, #0xb60] ;
001b12ff8: ldr      x0, [x8] ;
001b12ffc: ldrb     w8, [x0, #0x10a] ;
001b13000: tbz      w8, #0, #0x1b13010 ;
001b13004: ldr      w8, [x0, #0xbc] ;
001b13008: cbnz     w8, #0x1b13010 ;
001b1300c: bl       #0x3f3f378 ;
001b13010: adrp     x8, #0x51d9000 ;
001b13014: ldr      x8, [x8, #0x618] ;
001b13018: mov      x0, xzr ;
001b1301c: ldr      x1, [x8] ;
001b13020: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
001b13024: mov      x20, x0 ;
001b13028: cbnz     x20, #0x1b13030 ;
001b1302c: bl       #0x3f564f0 ;
001b13030: adrp     x8, #0x52ca000 ;
001b13034: ldr      x8, [x8, #0xf70] ;
001b13038: mov      x0, x20 ;
001b1303c: ldr      x1, [x8] ;
001b13040: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
001b13044: ldr      w19, [x19, #0x134] ;
001b13048: mov      x20, x0 ;
001b1304c: cbnz     x20, #0x1b13054 ;
001b13050: bl       #0x3f564f0 ;
001b13054: mov      x3, xzr ;
001b13058: mov      w2, #2 ;
001b1305c: mov      x0, x20 ;
001b13060: mov      w1, w19 ;
001b13064: sub      sp, x29, #0x20 ;
001b13068: ldp      x29, x30, [sp, #0x20] ;
001b1306c: ldp      x20, x19, [sp, #0x10] ;
001b13070: ldp      x22, x21, [sp], #0x30 ;
001b13074: b        #0x1b006fc ; CollegeModule$$SendWashingRoomOpt
