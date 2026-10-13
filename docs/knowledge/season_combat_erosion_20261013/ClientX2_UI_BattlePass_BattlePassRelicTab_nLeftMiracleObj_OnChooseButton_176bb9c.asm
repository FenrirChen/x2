; ClientX2.UI.BattlePass.BattlePassRelicTab.nLeftMiracleObj$$OnChooseButton
; RVA [0x176bb9c,0x176bc00), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 c1cb68e87acb0a48474465ebaee8c3bf1c959d15b0ff58b94325468507d659cc
00176bb9c: stp      x20, x19, [sp, #-0x20]! ;
00176bba0: stp      x29, x30, [sp, #0x10] ;
00176bba4: add      x29, sp, #0x10 ;
00176bba8: adrp     x20, #0x5577000 ;
00176bbac: ldrb     w8, [x20, #0x31] ;
00176bbb0: mov      x19, x0 ;
00176bbb4: tbnz     w8, #0, #0x176bbd0 ;
00176bbb8: adrp     x8, #0x5268000 ;
00176bbbc: ldr      x8, [x8, #0x238] ;
00176bbc0: ldr      w0, [x8] ;
00176bbc4: bl       #0x3f2aed0 ;
00176bbc8: mov      w8, #1 ;
00176bbcc: strb     w8, [x20, #0x31] ;
00176bbd0: ldr      x0, [x19, #0x60] ;
00176bbd4: cbz      x0, #0x176bbf4 ;
00176bbd8: adrp     x8, #0x5301000 ;
00176bbdc: ldr      w1, [x19, #0x50] ;
00176bbe0: ldr      x8, [x8, #0x388] ;
00176bbe4: ldr      x2, [x8] ;
00176bbe8: ldp      x29, x30, [sp, #0x10] ;
00176bbec: ldp      x20, x19, [sp], #0x20 ;
00176bbf0: b        #0x2621a2c ; System.Action<int>$$Invoke
00176bbf4: ldp      x29, x30, [sp, #0x10] ;
00176bbf8: ldp      x20, x19, [sp], #0x20 ;
00176bbfc: ret       ;
