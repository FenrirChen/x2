; CollegePurifyOptTab$$SendLockOpt
; RVA [0x1b136c4,0x1b1382c), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 98cf1c3f1b523c84c8880524165ee6c3e499857501b2309fea1b74670a3af9f4
001b136c4: stp      x22, x21, [sp, #-0x30]! ;
001b136c8: stp      x20, x19, [sp, #0x10] ;
001b136cc: stp      x29, x30, [sp, #0x20] ;
001b136d0: add      x29, sp, #0x20 ;
001b136d4: sub      sp, sp, #0x10 ;
001b136d8: adrp     x20, #0x5578000 ;
001b136dc: ldrb     w8, [x20, #0x8a6] ;
001b136e0: mov      x19, x0 ;
001b136e4: tbnz     w8, #0, #0x1b13700 ;
001b136e8: adrp     x8, #0x5238000 ;
001b136ec: ldr      x8, [x8, #0x998] ;
001b136f0: ldr      w0, [x8] ;
001b136f4: bl       #0x3f2aed0 ;
001b136f8: mov      w8, #1 ;
001b136fc: strb     w8, [x20, #0x8a6] ;
001b13700: ldr      w20, [x19, #0x17c] ;
001b13704: cmp      w20, #1 ;
001b13708: b.lt     #0x1b137a0 ;
001b1370c: adrp     x8, #0x5245000 ;
001b13710: adrp     x9, #0x5263000 ;
001b13714: ldr      x8, [x8, #0x828] ;
001b13718: ldr      x9, [x9, #0x430] ;
001b1371c: ldr      x22, [x8] ;
001b13720: ldr      x0, [x9] ;
001b13724: bl       #0x3f6452c ;
001b13728: mov      x3, xzr ;
001b1372c: mov      x1, x19 ;
001b13730: mov      x2, x22 ;
001b13734: mov      x21, x0 ;
001b13738: bl       #0x3e63db4 ; System.Action$$.ctor
001b1373c: adrp     x8, #0x5243000 ;
001b13740: ldr      x8, [x8, #0x7d0] ;
001b13744: ldr      x0, [x8] ;
001b13748: ldrb     w8, [x0, #0x10a] ;
001b1374c: tbz      w8, #0, #0x1b1375c ;
001b13750: ldr      w8, [x0, #0xbc] ;
001b13754: cbnz     w8, #0x1b1375c ;
001b13758: bl       #0x3f3f378 ;
001b1375c: adrp     x8, #0x525c000 ;
001b13760: ldr      x8, [x8, #0x120] ;  STRING_REF='UI_College_Building08'
001b13764: mov      x0, xzr ;
001b13768: mov      x3, xzr ;
001b1376c: mov      w5, wzr ;
001b13770: ldr      x6, [x8] ;
001b13774: mov      w4, #1 ;
001b13778: mov      w1, w20 ;
001b1377c: mov      x2, x21 ;
001b13780: mov      w7, wzr ;
001b13784: str      xzr, [sp] ;
001b13788: bl       #0x1348078 ; UIAPI$$CostDiamond
001b1378c: sub      sp, x29, #0x20 ;
001b13790: ldp      x29, x30, [sp, #0x20] ;
001b13794: ldp      x20, x19, [sp, #0x10] ;
001b13798: ldp      x22, x21, [sp], #0x30 ;
001b1379c: ret       ;
001b137a0: adrp     x8, #0x51ed000 ;
001b137a4: ldr      x8, [x8, #0xb60] ;
001b137a8: ldr      x0, [x8] ;
001b137ac: ldrb     w8, [x0, #0x10a] ;
001b137b0: tbz      w8, #0, #0x1b137c0 ;
001b137b4: ldr      w8, [x0, #0xbc] ;
001b137b8: cbnz     w8, #0x1b137c0 ;
001b137bc: bl       #0x3f3f378 ;
001b137c0: adrp     x8, #0x51d9000 ;
001b137c4: ldr      x8, [x8, #0x618] ;
001b137c8: mov      x0, xzr ;
001b137cc: ldr      x1, [x8] ;
001b137d0: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
001b137d4: mov      x20, x0 ;
001b137d8: cbnz     x20, #0x1b137e0 ;
001b137dc: bl       #0x3f564f0 ;
001b137e0: adrp     x8, #0x52ca000 ;
001b137e4: ldr      x8, [x8, #0xf70] ;
001b137e8: mov      x0, x20 ;
001b137ec: ldr      x1, [x8] ;
001b137f0: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
001b137f4: ldr      w20, [x19, #0x134] ;
001b137f8: ldr      x19, [x19, #0x180] ;
001b137fc: mov      x21, x0 ;
001b13800: cbnz     x21, #0x1b13808 ;
001b13804: bl       #0x3f564f0 ;
001b13808: mov      w2, #3 ;
001b1380c: mov      x0, x21 ;
001b13810: mov      w1, w20 ;
001b13814: mov      x3, x19 ;
001b13818: sub      sp, x29, #0x20 ;
001b1381c: ldp      x29, x30, [sp, #0x20] ;
001b13820: ldp      x20, x19, [sp, #0x10] ;
001b13824: ldp      x22, x21, [sp], #0x30 ;
001b13828: b        #0x1b006fc ; CollegeModule$$SendWashingRoomOpt
