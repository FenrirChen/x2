; BattlePassModule$$QueryBattlePassMissionData
; RVA [0x185c5a8,0x185c79c), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 1f07fdeaa3acf08f6434b4e9b97d162e74e0d41cbaa651c3b6959876705a1fb6
00185c5a8: stp      x20, x19, [sp, #-0x20]! ;
00185c5ac: stp      x29, x30, [sp, #0x10] ;
00185c5b0: add      x29, sp, #0x10 ;
00185c5b4: adrp     x20, #0x5577000 ;
00185c5b8: ldrb     w8, [x20, #0x6a4] ;
00185c5bc: mov      x19, x0 ;
00185c5c0: tbnz     w8, #0, #0x185c5dc ;
00185c5c4: adrp     x8, #0x520c000 ;
00185c5c8: ldr      x8, [x8, #0x190] ;
00185c5cc: ldr      w0, [x8] ;
00185c5d0: bl       #0x3f2aed0 ;
00185c5d4: mov      w8, #1 ;
00185c5d8: strb     w8, [x20, #0x6a4] ;
00185c5dc: ldr      w8, [x19, #0x134] ;
00185c5e0: cmp      w8, #0 ;
00185c5e4: b.gt     #0x185c688 ;
00185c5e8: adrp     x8, #0x52ed000 ;
00185c5ec: ldr      x8, [x8, #0xaf8] ;
00185c5f0: ldr      x0, [x8] ;
00185c5f4: ldrb     w8, [x0, #0x10a] ;
00185c5f8: tbz      w8, #0, #0x185c608 ;
00185c5fc: ldr      w8, [x0, #0xbc] ;
00185c600: cbnz     w8, #0x185c608 ;
00185c604: bl       #0x3f3f378 ;
00185c608: mov      x0, xzr ;
00185c60c: mov      x1, xzr ;
00185c610: bl       #0x1bde94c ; SeasonConfigManager$$get_Instance
00185c614: mov      x20, x0 ;
00185c618: cbnz     x20, #0x185c620 ;
00185c61c: bl       #0x3f564f0 ;
00185c620: mov      x1, xzr ;
00185c624: mov      x0, x20 ;
00185c628: bl       #0x1bded24 ; SeasonConfigManager$$GetAllItem
00185c62c: mov      x20, x0 ;
00185c630: cbnz     x20, #0x185c638 ;
00185c634: bl       #0x3f564f0 ;
00185c638: ldr      x20, [x20, #0x18] ;
00185c63c: cbz      x20, #0x185c688 ;
00185c640: adrp     x8, #0x52f6000 ;
00185c644: ldr      x8, [x8, #0x678] ;
00185c648: mov      x0, x20 ;
00185c64c: ldr      x1, [x8] ;
00185c650: bl       #0x3d51884 ; System.Collections.Generic.List<IEventSystemHandler>$$get_Count
00185c654: cmp      w0, #1 ;
00185c658: b.lt     #0x185c688 ;
00185c65c: adrp     x8, #0x5230000 ;
00185c660: ldr      x8, [x8, #0xc08] ;
00185c664: mov      w1, wzr ;
00185c668: mov      x0, x20 ;
00185c66c: ldr      x2, [x8] ;
00185c670: bl       #0x3d5188c ; System.Collections.Generic.List<IEventSystemHandler>$$get_Item
00185c674: mov      x20, x0 ;
00185c678: cbnz     x20, #0x185c680 ;
00185c67c: bl       #0x3f564f0 ;
00185c680: ldr      w8, [x20, #0x10] ;
00185c684: str      w8, [x19, #0x134] ;
00185c688: adrp     x8, #0x51ed000 ;
00185c68c: ldr      x8, [x8, #0xb60] ;
00185c690: ldr      x0, [x8] ;
00185c694: ldrb     w8, [x0, #0x10a] ;
00185c698: tbz      w8, #0, #0x185c6a8 ;
00185c69c: ldr      w8, [x0, #0xbc] ;
00185c6a0: cbnz     w8, #0x185c6a8 ;
00185c6a4: bl       #0x3f3f378 ;
00185c6a8: adrp     x8, #0x51d9000 ;
00185c6ac: ldr      x8, [x8, #0x618] ;
00185c6b0: mov      x0, xzr ;
00185c6b4: ldr      x1, [x8] ;
00185c6b8: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
00185c6bc: mov      x20, x0 ;
00185c6c0: cbnz     x20, #0x185c6c8 ;
00185c6c4: bl       #0x3f564f0 ;
00185c6c8: adrp     x8, #0x5252000 ;
00185c6cc: ldr      x8, [x8, #0xae0] ;
00185c6d0: mov      x0, x20 ;
00185c6d4: ldr      x1, [x8] ;
00185c6d8: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
00185c6dc: mov      x20, x0 ;
00185c6e0: cbnz     x20, #0x185c6e8 ;
00185c6e4: bl       #0x3f564f0 ;
00185c6e8: mov      w2, wzr ;
00185c6ec: mov      x3, xzr ;
00185c6f0: mov      w1, #0x37 ;
00185c6f4: mov      x0, x20 ;
00185c6f8: bl       #0x1317cf4 ; ActivityNoticeModule$$CheckActivityOpen
00185c6fc: tbz      w0, #0, #0x185c790 ;
00185c700: ldr      x8, [x19, #0x148] ;
00185c704: cbnz     x8, #0x185c728 ;
00185c708: adrp     x8, #0x527d000 ;
00185c70c: ldr      x8, [x8, #0xb30] ;
00185c710: ldr      x0, [x8] ;
00185c714: bl       #0x3f6452c ;
00185c718: mov      x1, xzr ;
00185c71c: mov      x20, x0 ;
00185c720: bl       #0x3c982f0 ; CommandX2.C2L_BattlePassMissionInfo$$.ctor
00185c724: str      x20, [x19, #0x148] ;
00185c728: adrp     x8, #0x5227000 ;
00185c72c: ldr      x8, [x8, #0x168] ;
00185c730: ldr      x0, [x8] ;
00185c734: ldrb     w8, [x0, #0x10a] ;
00185c738: tbz      w8, #0, #0x185c748 ;
00185c73c: ldr      w8, [x0, #0xbc] ;
00185c740: cbnz     w8, #0x185c748 ;
00185c744: bl       #0x3f3f378 ;
00185c748: mov      x0, xzr ;
00185c74c: mov      x1, xzr ;
00185c750: bl       #0x141a6c8 ; MarsNetManager$$get_Instance
00185c754: ldr      x19, [x19, #0x148] ;
00185c758: mov      x20, x0 ;
00185c75c: cbnz     x20, #0x185c764 ;
00185c760: bl       #0x3f564f0 ;
00185c764: adrp     x8, #0x51d0000 ;
00185c768: ldr      x8, [x8, #0x18] ;
00185c76c: mov      w3, wzr ;
00185c770: mov      w4, wzr ;
00185c774: mov      w2, #3 ;
00185c778: ldr      x5, [x8] ;
00185c77c: ldp      x29, x30, [sp, #0x10] ;
00185c780: mov      x0, x20 ;
00185c784: mov      x1, x19 ;
00185c788: ldp      x20, x19, [sp], #0x20 ;
00185c78c: b        #0x233d7ac ; MarsNetManager$$Send<C2L_ReissueDialogReciveInfo>
00185c790: ldp      x29, x30, [sp, #0x10] ;
00185c794: ldp      x20, x19, [sp], #0x20 ;
00185c798: ret       ;
