; BattlePassTalentView.<>c__DisplayClass21_0$$<OnResetTalent>b__0
; RVA [0x14c68a4,0x14c6a24), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 77fa0cc66f4c52e6b365fc1836da9e5cd8a8375434ff0533511d5e77a0c412dc
0014c68a4: stp      x22, x21, [sp, #-0x30]! ;
0014c68a8: stp      x20, x19, [sp, #0x10] ;
0014c68ac: stp      x29, x30, [sp, #0x20] ;
0014c68b0: add      x29, sp, #0x20 ;
0014c68b4: adrp     x20, #0x5575000 ;
0014c68b8: ldrb     w8, [x20, #0xdf3] ;
0014c68bc: mov      x19, x0 ;
0014c68c0: tbnz     w8, #0, #0x14c68dc ;
0014c68c4: adrp     x8, #0x52f7000 ;
0014c68c8: ldr      x8, [x8, #0xde8] ;
0014c68cc: ldr      w0, [x8] ;
0014c68d0: bl       #0x3f2aed0 ;
0014c68d4: mov      w8, #1 ;
0014c68d8: strb     w8, [x20, #0xdf3] ;
0014c68dc: adrp     x8, #0x528b000 ;
0014c68e0: ldr      x8, [x8, #0x2e0] ;
0014c68e4: ldr      x0, [x8] ;
0014c68e8: ldrb     w8, [x0, #0x10a] ;
0014c68ec: tbz      w8, #0, #0x14c68fc ;
0014c68f0: ldr      w8, [x0, #0xbc] ;
0014c68f4: cbnz     w8, #0x14c68fc ;
0014c68f8: bl       #0x3f3f378 ;
0014c68fc: mov      x0, xzr ;
0014c6900: mov      w1, #1 ;
0014c6904: mov      x2, xzr ;
0014c6908: bl       #0x154933c ; GameAPI$$GetCurrencyNum
0014c690c: ldr      x21, [x19, #0x10] ;
0014c6910: mov      w20, w0 ;
0014c6914: cbnz     x21, #0x14c691c ;
0014c6918: bl       #0x3f564f0 ;
0014c691c: ldr      w8, [x21, #0xc4] ;
0014c6920: ldr      w9, [x19, #0x18] ;
0014c6924: mul      w8, w9, w8 ;
0014c6928: cmp      w20, w8 ;
0014c692c: b.ge     #0x14c6974 ;
0014c6930: adrp     x8, #0x5243000 ;
0014c6934: ldr      x8, [x8, #0x7d0] ;
0014c6938: ldr      x0, [x8] ;
0014c693c: ldrb     w8, [x0, #0x10a] ;
0014c6940: tbz      w8, #0, #0x14c6950 ;
0014c6944: ldr      w8, [x0, #0xbc] ;
0014c6948: cbnz     w8, #0x14c6950 ;
0014c694c: bl       #0x3f3f378 ;
0014c6950: ldp      x29, x30, [sp, #0x20] ;
0014c6954: ldp      x20, x19, [sp, #0x10] ;
0014c6958: mov      w1, #0xc70000 ;
0014c695c: mov      x0, xzr ;
0014c6960: movk     w1, #0xe491 ;
0014c6964: mov      w2, wzr ;
0014c6968: mov      x3, xzr ;
0014c696c: ldp      x22, x21, [sp], #0x30 ;
0014c6970: b        #0x134790c ; UIAPI$$ShowSingleBubbleMsg
0014c6974: adrp     x8, #0x51ed000 ;
0014c6978: ldr      x8, [x8, #0xb60] ;
0014c697c: ldr      x0, [x8] ;
0014c6980: ldrb     w8, [x0, #0x10a] ;
0014c6984: tbz      w8, #0, #0x14c6994 ;
0014c6988: ldr      w8, [x0, #0xbc] ;
0014c698c: cbnz     w8, #0x14c6994 ;
0014c6990: bl       #0x3f3f378 ;
0014c6994: adrp     x8, #0x51d9000 ;
0014c6998: ldr      x8, [x8, #0x618] ;
0014c699c: mov      x0, xzr ;
0014c69a0: ldr      x1, [x8] ;
0014c69a4: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
0014c69a8: mov      x20, x0 ;
0014c69ac: cbnz     x20, #0x14c69b4 ;
0014c69b0: bl       #0x3f564f0 ;
0014c69b4: adrp     x8, #0x5246000 ;
0014c69b8: ldr      x8, [x8, #0xfd8] ;
0014c69bc: mov      x0, x20 ;
0014c69c0: ldr      x1, [x8] ;
0014c69c4: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
0014c69c8: ldr      x21, [x19, #0x20] ;
0014c69cc: mov      x20, x0 ;
0014c69d0: cbnz     x21, #0x14c69d8 ;
0014c69d4: bl       #0x3f564f0 ;
0014c69d8: ldr      w21, [x21, #0x6c] ;
0014c69dc: cbnz     x20, #0x14c69e4 ;
0014c69e0: bl       #0x3f564f0 ;
0014c69e4: mov      x2, xzr ;
0014c69e8: mov      x0, x20 ;
0014c69ec: mov      w1, w21 ;
0014c69f0: bl       #0x185e888 ; BattlePassModule$$SendBattlePassTalentReset
0014c69f4: ldr      x20, [x19, #0x10] ;
0014c69f8: cbnz     x20, #0x14c6a00 ;
0014c69fc: bl       #0x3f564f0 ;
0014c6a00: strb     wzr, [x20, #0xc8] ;
0014c6a04: ldr      x19, [x19, #0x10] ;
0014c6a08: cbnz     x19, #0x14c6a10 ;
0014c6a0c: bl       #0x3f564f0 ;
0014c6a10: mov      x0, x19 ;
0014c6a14: ldp      x29, x30, [sp, #0x20] ;
0014c6a18: ldp      x20, x19, [sp, #0x10] ;
0014c6a1c: ldp      x22, x21, [sp], #0x30 ;
0014c6a20: b        #0x14c3528 ; BattlePassTalentView$$RefreshResetState
