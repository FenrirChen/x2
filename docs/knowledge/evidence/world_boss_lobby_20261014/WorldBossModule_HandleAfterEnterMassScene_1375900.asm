; WorldBossModule$$HandleAfterEnterMassScene
; RVA [0x1375900,0x13759e4), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 2f29b9be6001e07fa7050dcf8202390ccd3794e43f2e277f896878dc0dd9a4aa
001375900: stp      x20, x19, [sp, #-0x20]! ;
001375904: stp      x29, x30, [sp, #0x10] ;
001375908: add      x29, sp, #0x10 ;
00137590c: adrp     x20, #0x5575000 ;
001375910: ldrb     w8, [x20, #0x563] ;
001375914: mov      x19, x0 ;
001375918: tbnz     w8, #0, #0x1375934 ;
00137591c: adrp     x8, #0x525a000 ;
001375920: ldr      x8, [x8, #0x978] ;
001375924: ldr      w0, [x8] ;
001375928: bl       #0x3f2aed0 ;
00137592c: mov      w8, #1 ;
001375930: strb     w8, [x20, #0x563] ;
001375934: ldr      x8, [x19, #0x60] ;
001375938: cbz      x8, #0x1375978 ;
00137593c: ldr      w8, [x8, #0x30] ;
001375940: sub      w9, w8, #1 ;
001375944: add      w8, w8, #5 ;
001375948: cmp      w9, #4 ;
00137594c: csel     w8, w8, wzr, lo ;
001375950: cmp      w8, #9 ;
001375954: b.eq     #0x13759b8 ;
001375958: cmp      w8, #8 ;
00137595c: b.eq     #0x13759c8 ;
001375960: cmp      w8, #7 ;
001375964: b.ne     #0x13759d8 ;
001375968: ldp      x29, x30, [sp, #0x10] ;
00137596c: mov      x0, x19 ;
001375970: ldp      x20, x19, [sp], #0x20 ;
001375974: b        #0x1376090 ; WorldBossModule$$StartEnterTimer
001375978: adrp     x8, #0x5207000 ;
00137597c: ldr      x8, [x8, #0x5a0] ;
001375980: ldr      x0, [x8] ;
001375984: ldrb     w8, [x0, #0x10a] ;
001375988: tbz      w8, #0, #0x1375998 ;
00137598c: ldr      w8, [x0, #0xbc] ;
001375990: cbnz     w8, #0x1375998 ;
001375994: bl       #0x3f3f378 ;
001375998: adrp     x8, #0x523c000 ;
00137599c: ldr      x8, [x8, #0x2a8] ;  STRING_REF='HandleAfterEnterMassScene, CurChallengeBossInfo为null'
0013759a0: mov      x0, xzr ;
0013759a4: mov      x2, xzr ;
0013759a8: ldr      x1, [x8] ;
0013759ac: ldp      x29, x30, [sp, #0x10] ;
0013759b0: ldp      x20, x19, [sp], #0x20 ;
0013759b4: b        #0x3e45c84 ; CommonX2.Debug$$LogError
0013759b8: ldp      x29, x30, [sp, #0x10] ;
0013759bc: mov      x0, x19 ;
0013759c0: ldp      x20, x19, [sp], #0x20 ;
0013759c4: b        #0x13762c8 ; WorldBossModule$$DoBossDisMissPerformance
0013759c8: ldp      x29, x30, [sp, #0x10] ;
0013759cc: mov      x0, x19 ;
0013759d0: ldp      x20, x19, [sp], #0x20 ;
0013759d4: b        #0x13759e4 ; WorldBossModule$$DoBossOverPerformance
0013759d8: ldp      x29, x30, [sp, #0x10] ;
0013759dc: ldp      x20, x19, [sp], #0x20 ;
0013759e0: ret       ;
