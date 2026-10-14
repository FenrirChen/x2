; WorldBossModule$$OnHandleW2CDoBossAct
; RVA [0x13755a0,0x1375874), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 ee4f6f113019f1b882d8eea95b321b572f6442cfa7c01a113949789e3cde0180
0013755a0: stp      x22, x21, [sp, #-0x30]! ;
0013755a4: stp      x20, x19, [sp, #0x10] ;
0013755a8: stp      x29, x30, [sp, #0x20] ;
0013755ac: add      x29, sp, #0x20 ;
0013755b0: sub      sp, sp, #0x10 ;
0013755b4: adrp     x21, #0x5575000 ;
0013755b8: ldrb     w8, [x21, #0x54e] ;
0013755bc: mov      x20, x1 ;
0013755c0: mov      x19, x0 ;
0013755c4: tbnz     w8, #0, #0x13755e0 ;
0013755c8: adrp     x8, #0x52e9000 ;
0013755cc: ldr      x8, [x8, #0x168] ;
0013755d0: ldr      w0, [x8] ;
0013755d4: bl       #0x3f2aed0 ;
0013755d8: mov      w8, #1 ;
0013755dc: strb     w8, [x21, #0x54e] ;
0013755e0: cbz      x20, #0x13757ac ;
0013755e4: adrp     x9, #0x52f7000 ;
0013755e8: ldr      x9, [x9, #0x750] ;
0013755ec: ldr      x8, [x20] ;
0013755f0: ldr      x1, [x9] ;
0013755f4: ldrb     w10, [x8, #0x104] ;
0013755f8: ldrb     w9, [x1, #0x104] ;
0013755fc: cmp      w10, w9 ;
001375600: b.lo     #0x1375618 ;
001375604: ldr      x10, [x8, #0xb0] ;
001375608: add      x9, x10, x9, lsl #3 ;
00137560c: ldur     x9, [x9, #-8] ;
001375610: cmp      x9, x1 ;
001375614: b.eq     #0x137564c ;
001375618: ldr      x0, [x8, #0x30] ;
00137561c: add      x8, sp, #8 ;
001375620: bl       #0x3f81f90 ;
001375624: ldr      x0, [sp, #8] ;
001375628: bl       #0x3f570a8 ;
00137562c: mov      x1, xzr ;
001375630: bl       #0x3f563d4 ;
001375634: add      x0, sp, #8 ;
001375638: bl       #0x3f8a0d0 ;
00137563c: bl       #0x3f564f0 ;
001375640: mov      x20, xzr ;
001375644: mov      w21, #1 ;
001375648: b        #0x1375650 ;
00137564c: mov      w21, wzr ;
001375650: ldr      w9, [x20, #0x10] ;
001375654: ldr      x8, [x19, #0x60] ;
001375658: cmp      w9, #0xa ;
00137565c: b.ne     #0x1375750 ;
001375660: cbz      x8, #0x13757ac ;
001375664: ldr      x1, [x20, #0x28] ;
001375668: mov      x0, x19 ;
00137566c: bl       #0x1374020 ; WorldBossModule$$UpdateChallengeWorldBossInfoChange
001375670: ldr      w8, [x20, #0x20] ;
001375674: sub      w9, w8, #1 ;
001375678: add      w8, w8, #5 ;
00137567c: cmp      w9, #3 ;
001375680: csel     w8, w8, wzr, lo ;
001375684: cmp      w8, #8 ;
001375688: b.eq     #0x13757c0 ;
00137568c: cmp      w8, #7 ;
001375690: b.eq     #0x1375828 ;
001375694: cmp      w8, #6 ;
001375698: b.ne     #0x13757ac ;
00137569c: adrp     x8, #0x51f1000 ;
0013756a0: ldr      x8, [x8, #0x908] ;
0013756a4: ldr      x0, [x8] ;
0013756a8: ldrb     w8, [x0, #0x10a] ;
0013756ac: tbz      w8, #0, #0x13756bc ;
0013756b0: ldr      w8, [x0, #0xbc] ;
0013756b4: cbnz     w8, #0x13756bc ;
0013756b8: bl       #0x3f3f378 ;
0013756bc: mov      x0, xzr ;
0013756c0: mov      x1, xzr ;
0013756c4: bl       #0x1e7c0bc ; WorldBossNetManager$$get_Instance
0013756c8: mov      x20, x0 ;
0013756cc: cbnz     x20, #0x13756d4 ;
0013756d0: bl       #0x3f564f0 ;
0013756d4: mov      x2, xzr ;
0013756d8: mov      w1, #1 ;
0013756dc: mov      x0, x20 ;
0013756e0: bl       #0x1e7dbe4 ; WorldBossNetManager$$JoinResult
0013756e4: mov      x0, x19 ;
0013756e8: bl       #0x136be34 ; WorldBossModule$$SendSelectHero
0013756ec: adrp     x8, #0x52e3000 ;
0013756f0: ldr      x8, [x8, #0x530] ;
0013756f4: ldr      x0, [x8] ;
0013756f8: ldrb     w8, [x0, #0x10a] ;
0013756fc: tbz      w8, #0, #0x137570c ;
001375700: ldr      w8, [x0, #0xbc] ;
001375704: cbnz     w8, #0x137570c ;
001375708: bl       #0x3f3f378 ;
00137570c: mov      x0, xzr ;
001375710: mov      x1, xzr ;
001375714: bl       #0x1379e68 ; GameAppImpl$$GetInstance
001375718: ldr      x21, [x19, #0x60] ;
00137571c: mov      x20, x0 ;
001375720: cbnz     x21, #0x1375728 ;
001375724: bl       #0x3f564f0 ;
001375728: ldrb     w8, [x21, #0x50] ;
00137572c: cbz      w8, #0x1375834 ;
001375730: cbz      x20, #0x137584c ;
001375734: ldr      w8, [x20, #0x28] ;
001375738: cbz      w8, #0x1375840 ;
00137573c: cmp      w8, #2 ;
001375740: b.ne     #0x13757ac ;
001375744: mov      x0, x19 ;
001375748: bl       #0x1375900 ; WorldBossModule$$HandleAfterEnterMassScene
00137574c: b        #0x13757ac ;
001375750: cbz      x8, #0x137576c ;
001375754: ldr      x1, [x8, #0x10] ;
001375758: ldr      x2, [x8, #0x20] ;
00137575c: mov      w3, wzr ;
001375760: mov      w4, #1 ;
001375764: mov      x0, x19 ;
001375768: bl       #0x136f0a4 ; WorldBossModule$$QueryBossData
00137576c: cbz      w21, #0x1375774 ;
001375770: bl       #0x3f564f0 ;
001375774: adrp     x8, #0x528b000 ;
001375778: ldr      x8, [x8, #0x2e0] ;
00137577c: ldr      w19, [x20, #0x10] ;
001375780: ldr      x0, [x8] ;
001375784: ldrb     w8, [x0, #0x10a] ;
001375788: tbz      w8, #0, #0x1375798 ;
00137578c: ldr      w8, [x0, #0xbc] ;
001375790: cbnz     w8, #0x1375798 ;
001375794: bl       #0x3f3f378 ;
001375798: mov      x0, xzr ;
00137579c: mov      x2, xzr ;
0013757a0: mov      w1, w19 ;
0013757a4: mov      x3, xzr ;
0013757a8: bl       #0x1529eb8 ; GameAPI$$ShowErrorCodeBubble
0013757ac: sub      sp, x29, #0x20 ;
0013757b0: ldp      x29, x30, [sp, #0x20] ;
0013757b4: ldp      x20, x19, [sp, #0x10] ;
0013757b8: ldp      x22, x21, [sp], #0x30 ;
0013757bc: ret       ;
0013757c0: ldr      x8, [x20, #0x28] ;
0013757c4: cbz      x8, #0x13757ac ;
0013757c8: mov      x0, xzr ;
0013757cc: mov      x1, xzr ;
0013757d0: bl       #0x18d3144 ; LogicX2.LogicBattle$$get_Current
0013757d4: mov      x19, x0 ;
0013757d8: cbz      x19, #0x13757ac ;
0013757dc: adrp     x8, #0x5300000 ;
0013757e0: ldr      x8, [x8, #0xcc0] ;
0013757e4: ldr      x0, [x8] ;
0013757e8: bl       #0x3f6452c ;
0013757ec: mov      x1, xzr ;
0013757f0: mov      x21, x0 ;
0013757f4: bl       #0x1c5b6d4 ; LogicX2Command.WorldBossHPSync$$.ctor
0013757f8: ldr      x20, [x20, #0x28] ;
0013757fc: cbnz     x20, #0x1375804 ;
001375800: bl       #0x3f564f0 ;
001375804: ldr      x20, [x20, #0x60] ;
001375808: cbnz     x21, #0x1375810 ;
00137580c: bl       #0x3f564f0 ;
001375810: mov      x2, xzr ;
001375814: mov      x0, x19 ;
001375818: mov      x1, x21 ;
00137581c: str      x20, [x21, #0x18] ;
001375820: bl       #0x18f6b30 ; LogicX2.LogicBattle$$OnInput
001375824: b        #0x13757ac ;
001375828: mov      x0, x19 ;
00137582c: bl       #0x1375200 ; WorldBossModule$$LeaveWorldBoss
001375830: b        #0x13757ac ;
001375834: cbz      x20, #0x1375854 ;
001375838: ldr      w8, [x20, #0x28] ;
00137583c: cbnz     w8, #0x13757ac ;
001375840: mov      x0, x19 ;
001375844: bl       #0x13759e4 ; WorldBossModule$$DoBossOverPerformance
001375848: b        #0x13757ac ;
00137584c: bl       #0x1375874 ; WorldBossModule$$EnterMassScene
001375850: b        #0x13757ac ;
001375854: mov      x0, x19 ;
001375858: bl       #0x1375cd4 ; WorldBossModule$$StartBossBattle
00137585c: b        #0x13757ac ;
001375860: mov      x19, x0 ;
001375864: add      x0, sp, #8 ;
001375868: bl       #0x3f8a0d0 ;
00137586c: mov      x0, x19 ;
001375870: bl       #0x113f690 ;
