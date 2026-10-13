; CollegePurifyOptTab$$SendAddOpt
; RVA [0x1b12d78,0x1b12edc), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 eccc5895ca4dc229257ac677d8632f05e507540e9e5fb5a32d873a62fbcceea2
001b12d78: stp      x22, x21, [sp, #-0x30]! ;
001b12d7c: stp      x20, x19, [sp, #0x10] ;
001b12d80: stp      x29, x30, [sp, #0x20] ;
001b12d84: add      x29, sp, #0x20 ;
001b12d88: sub      sp, sp, #0x10 ;
001b12d8c: adrp     x20, #0x5578000 ;
001b12d90: ldrb     w8, [x20, #0x8a3] ;
001b12d94: mov      x19, x0 ;
001b12d98: tbnz     w8, #0, #0x1b12db4 ;
001b12d9c: adrp     x8, #0x530e000 ;
001b12da0: ldr      x8, [x8, #0xfe0] ;
001b12da4: ldr      w0, [x8] ;
001b12da8: bl       #0x3f2aed0 ;
001b12dac: mov      w8, #1 ;
001b12db0: strb     w8, [x20, #0x8a3] ;
001b12db4: ldr      w20, [x19, #0x17c] ;
001b12db8: cmp      w20, #1 ;
001b12dbc: b.lt     #0x1b12e54 ;
001b12dc0: adrp     x8, #0x521c000 ;
001b12dc4: adrp     x9, #0x5263000 ;
001b12dc8: ldr      x8, [x8, #0x328] ;
001b12dcc: ldr      x9, [x9, #0x430] ;
001b12dd0: ldr      x22, [x8] ;
001b12dd4: ldr      x0, [x9] ;
001b12dd8: bl       #0x3f6452c ;
001b12ddc: mov      x3, xzr ;
001b12de0: mov      x1, x19 ;
001b12de4: mov      x2, x22 ;
001b12de8: mov      x21, x0 ;
001b12dec: bl       #0x3e63db4 ; System.Action$$.ctor
001b12df0: adrp     x8, #0x5243000 ;
001b12df4: ldr      x8, [x8, #0x7d0] ;
001b12df8: ldr      x0, [x8] ;
001b12dfc: ldrb     w8, [x0, #0x10a] ;
001b12e00: tbz      w8, #0, #0x1b12e10 ;
001b12e04: ldr      w8, [x0, #0xbc] ;
001b12e08: cbnz     w8, #0x1b12e10 ;
001b12e0c: bl       #0x3f3f378 ;
001b12e10: adrp     x8, #0x525c000 ;
001b12e14: ldr      x8, [x8, #0x120] ;  STRING_REF='UI_College_Building08'
001b12e18: mov      x0, xzr ;
001b12e1c: mov      x3, xzr ;
001b12e20: mov      w5, wzr ;
001b12e24: ldr      x6, [x8] ;
001b12e28: mov      w4, #1 ;
001b12e2c: mov      w1, w20 ;
001b12e30: mov      x2, x21 ;
001b12e34: mov      w7, wzr ;
001b12e38: str      xzr, [sp] ;
001b12e3c: bl       #0x1348078 ; UIAPI$$CostDiamond
001b12e40: sub      sp, x29, #0x20 ;
001b12e44: ldp      x29, x30, [sp, #0x20] ;
001b12e48: ldp      x20, x19, [sp, #0x10] ;
001b12e4c: ldp      x22, x21, [sp], #0x30 ;
001b12e50: ret       ;
001b12e54: adrp     x8, #0x51ed000 ;
001b12e58: ldr      x8, [x8, #0xb60] ;
001b12e5c: ldr      x0, [x8] ;
001b12e60: ldrb     w8, [x0, #0x10a] ;
001b12e64: tbz      w8, #0, #0x1b12e74 ;
001b12e68: ldr      w8, [x0, #0xbc] ;
001b12e6c: cbnz     w8, #0x1b12e74 ;
001b12e70: bl       #0x3f3f378 ;
001b12e74: adrp     x8, #0x51d9000 ;
001b12e78: ldr      x8, [x8, #0x618] ;
001b12e7c: mov      x0, xzr ;
001b12e80: ldr      x1, [x8] ;
001b12e84: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
001b12e88: mov      x20, x0 ;
001b12e8c: cbnz     x20, #0x1b12e94 ;
001b12e90: bl       #0x3f564f0 ;
001b12e94: adrp     x8, #0x52ca000 ;
001b12e98: ldr      x8, [x8, #0xf70] ;
001b12e9c: mov      x0, x20 ;
001b12ea0: ldr      x1, [x8] ;
001b12ea4: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
001b12ea8: ldr      w19, [x19, #0x134] ;
001b12eac: mov      x20, x0 ;
001b12eb0: cbnz     x20, #0x1b12eb8 ;
001b12eb4: bl       #0x3f564f0 ;
001b12eb8: mov      x3, xzr ;
001b12ebc: mov      w2, #1 ;
001b12ec0: mov      x0, x20 ;
001b12ec4: mov      w1, w19 ;
001b12ec8: sub      sp, x29, #0x20 ;
001b12ecc: ldp      x29, x30, [sp, #0x20] ;
001b12ed0: ldp      x20, x19, [sp, #0x10] ;
001b12ed4: ldp      x22, x21, [sp], #0x30 ;
001b12ed8: b        #0x1b006fc ; CollegeModule$$SendWashingRoomOpt
