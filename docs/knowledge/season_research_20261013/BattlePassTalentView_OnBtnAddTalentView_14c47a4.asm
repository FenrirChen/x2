; BattlePassTalentView$$OnBtnAddTalentView
; RVA [0x14c47a4,0x14c4960), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 489952f4cb861cf757f24a5da26035a7431696372aecdeabf5e33a9292abdb37
0014c47a4: stp      x26, x25, [sp, #-0x50]! ;
0014c47a8: stp      x24, x23, [sp, #0x10] ;
0014c47ac: stp      x22, x21, [sp, #0x20] ;
0014c47b0: stp      x20, x19, [sp, #0x30] ;
0014c47b4: stp      x29, x30, [sp, #0x40] ;
0014c47b8: add      x29, sp, #0x40 ;
0014c47bc: adrp     x21, #0x5575000 ;
0014c47c0: ldrb     w8, [x21, #0xde0] ;
0014c47c4: mov      x20, x1 ;
0014c47c8: mov      x19, x0 ;
0014c47cc: tbnz     w8, #0, #0x14c47e8 ;
0014c47d0: adrp     x8, #0x52b7000 ;
0014c47d4: ldr      x8, [x8, #0x280] ;
0014c47d8: ldr      w0, [x8] ;
0014c47dc: bl       #0x3f2aed0 ;
0014c47e0: mov      w8, #1 ;
0014c47e4: strb     w8, [x21, #0xde0] ;
0014c47e8: adrp     x23, #0x521b000 ;
0014c47ec: adrp     x24, #0x51df000 ;
0014c47f0: ldr      x23, [x23, #0xa68] ;
0014c47f4: ldr      x24, [x24, #0x1f0] ;
0014c47f8: mov      w21, wzr ;
0014c47fc: mov      w25, wzr ;
0014c4800: b        #0x14c4808 ;
0014c4804: add      w21, w21, #1 ;
0014c4808: ldr      x22, [x19, #0xb8] ;
0014c480c: cbnz     x22, #0x14c4814 ;
0014c4810: bl       #0x3f564f0 ;
0014c4814: ldr      x1, [x23] ;
0014c4818: mov      x0, x22 ;
0014c481c: bl       #0x3d51884 ; System.Collections.Generic.List<IEventSystemHandler>$$get_Count
0014c4820: cmp      w21, w0 ;
0014c4824: b.ge     #0x14c48a0 ;
0014c4828: ldr      x22, [x19, #0xb8] ;
0014c482c: cbnz     x22, #0x14c4834 ;
0014c4830: bl       #0x3f564f0 ;
0014c4834: ldr      x2, [x24] ;
0014c4838: mov      x0, x22 ;
0014c483c: mov      w1, w21 ;
0014c4840: bl       #0x3d5188c ; System.Collections.Generic.List<IEventSystemHandler>$$get_Item
0014c4844: mov      x22, x0 ;
0014c4848: cbnz     x22, #0x14c4850 ;
0014c484c: bl       #0x3f564f0 ;
0014c4850: ldr      w22, [x22, #0x10] ;
0014c4854: cbnz     x20, #0x14c485c ;
0014c4858: bl       #0x3f564f0 ;
0014c485c: ldr      w8, [x20, #0x6c] ;
0014c4860: cmp      w22, w8 ;
0014c4864: b.ne     #0x14c4804 ;
0014c4868: ldr      x22, [x19, #0xb8] ;
0014c486c: cbnz     x22, #0x14c4874 ;
0014c4870: bl       #0x3f564f0 ;
0014c4874: ldr      x2, [x24] ;
0014c4878: mov      x0, x22 ;
0014c487c: mov      w1, w21 ;
0014c4880: bl       #0x3d5188c ; System.Collections.Generic.List<IEventSystemHandler>$$get_Item
0014c4884: ldr      w25, [x20, #0x68] ;
0014c4888: mov      x22, x0 ;
0014c488c: cbnz     x22, #0x14c4894 ;
0014c4890: bl       #0x3f564f0 ;
0014c4894: str      w25, [x22, #0x14] ;
0014c4898: mov      w25, #1 ;
0014c489c: b        #0x14c4804 ;
0014c48a0: and      w8, w25, #1 ;
0014c48a4: tbnz     w8, #0, #0x14c491c ;
0014c48a8: adrp     x8, #0x5268000 ;
0014c48ac: ldr      x8, [x8, #0xc00] ;
0014c48b0: ldr      x0, [x8] ;
0014c48b4: bl       #0x3f6452c ;
0014c48b8: mov      x1, xzr ;
0014c48bc: mov      x21, x0 ;
0014c48c0: bl       #0x397a434 ; CommandX2.TalentLevel$$.ctor
0014c48c4: cbnz     x20, #0x14c48cc ;
0014c48c8: bl       #0x3f564f0 ;
0014c48cc: ldr      w22, [x20, #0x6c] ;
0014c48d0: cbz      x21, #0x14c48e0 ;
0014c48d4: str      w22, [x21, #0x10] ;
0014c48d8: ldr      w20, [x20, #0x68] ;
0014c48dc: b        #0x14c48f4 ;
0014c48e0: bl       #0x3f564f0 ;
0014c48e4: mov      w8, #0x10 ;
0014c48e8: str      w22, [x8] ;
0014c48ec: ldr      w20, [x20, #0x68] ;
0014c48f0: bl       #0x3f564f0 ;
0014c48f4: str      w20, [x21, #0x14] ;
0014c48f8: ldr      x20, [x19, #0xb8] ;
0014c48fc: cbnz     x20, #0x14c4904 ;
0014c4900: bl       #0x3f564f0 ;
0014c4904: adrp     x8, #0x525f000 ;
0014c4908: ldr      x8, [x8, #0xc8] ;
0014c490c: mov      x0, x20 ;
0014c4910: mov      x1, x21 ;
0014c4914: ldr      x2, [x8] ;
0014c4918: bl       #0x3d4f3b4 ; System.Collections.Generic.List<FutureErrorCallback>$$Add
0014c491c: ldr      w8, [x19, #0xc0] ;
0014c4920: mov      x0, x19 ;
0014c4924: add      w8, w8, #1 ;
0014c4928: str      w8, [x19, #0xc0] ;
0014c492c: bl       #0x14c3df8 ; BattlePassTalentView$$RefreshPointView
0014c4930: mov      x0, x19 ;
0014c4934: bl       #0x14c41dc ; BattlePassTalentView$$RefreshTalentStatus
0014c4938: mov      x0, x19 ;
0014c493c: bl       #0x14c4314 ; BattlePassTalentView$$RefreshUpDownBtn
0014c4940: strb     wzr, [x19, #0xc8] ;
0014c4944: mov      x0, x19 ;
0014c4948: ldp      x29, x30, [sp, #0x40] ;
0014c494c: ldp      x20, x19, [sp, #0x30] ;
0014c4950: ldp      x22, x21, [sp, #0x20] ;
0014c4954: ldp      x24, x23, [sp, #0x10] ;
0014c4958: ldp      x26, x25, [sp], #0x50 ;
0014c495c: b        #0x14c3528 ; BattlePassTalentView$$RefreshResetState
