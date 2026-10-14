; BattlePassTalentView.TalentItemData$$AddPoint
; RVA [0x14c7194,0x14c7208), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 527cdf036129ed4158428c11c0261faaa07d6b6e21d59004c32d89efde3efd1c
0014c7194: stp      x20, x19, [sp, #-0x20]! ;
0014c7198: stp      x29, x30, [sp, #0x10] ;
0014c719c: add      x29, sp, #0x10 ;
0014c71a0: adrp     x20, #0x5575000 ;
0014c71a4: ldrb     w8, [x20, #0xdfc] ;
0014c71a8: mov      x19, x0 ;
0014c71ac: tbnz     w8, #0, #0x14c71c8 ;
0014c71b0: adrp     x8, #0x52eb000 ;
0014c71b4: ldr      x8, [x8, #0x330] ;
0014c71b8: ldr      w0, [x8] ;
0014c71bc: bl       #0x3f2aed0 ;
0014c71c0: mov      w8, #1 ;
0014c71c4: strb     w8, [x20, #0xdfc] ;
0014c71c8: ldr      w8, [x19, #0x68] ;
0014c71cc: mov      x0, x19 ;
0014c71d0: add      w8, w8, #1 ;
0014c71d4: str      w8, [x19, #0x68] ;
0014c71d8: bl       #0x14c6ee8 ; BattlePassTalentView.TalentItemData$$RefreshLevelNum
0014c71dc: ldr      x20, [x19, #0x78] ;
0014c71e0: cbnz     x20, #0x14c71e8 ;
0014c71e4: bl       #0x3f564f0 ;
0014c71e8: adrp     x8, #0x526e000 ;
0014c71ec: ldr      x8, [x8, #0x288] ;
0014c71f0: mov      x0, x20 ;
0014c71f4: mov      x1, x19 ;
0014c71f8: ldr      x2, [x8] ;
0014c71fc: ldp      x29, x30, [sp, #0x10] ;
0014c7200: ldp      x20, x19, [sp], #0x20 ;
0014c7204: b        #0x262251c ; System.Action<Level>$$Invoke
