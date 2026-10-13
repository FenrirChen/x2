; BattlePassModule$$OnHandleActivitySync
; RVA [0x185be58,0x185c0bc), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 ad6dabe45a280455152d00c41aa75957cb4a9003691a594bba9377f52bc0b36a
00185be58: stp      x28, x27, [sp, #-0x60]! ;
00185be5c: stp      x26, x25, [sp, #0x10] ;
00185be60: stp      x24, x23, [sp, #0x20] ;
00185be64: stp      x22, x21, [sp, #0x30] ;
00185be68: stp      x20, x19, [sp, #0x40] ;
00185be6c: stp      x29, x30, [sp, #0x50] ;
00185be70: add      x29, sp, #0x50 ;
00185be74: adrp     x21, #0x5577000 ;
00185be78: ldrb     w8, [x21, #0x676] ;
00185be7c: mov      x20, x1 ;
00185be80: mov      x19, x0 ;
00185be84: tbnz     w8, #0, #0x185bea0 ;
00185be88: adrp     x8, #0x52af000 ;
00185be8c: ldr      x8, [x8, #0xc50] ;
00185be90: ldr      w0, [x8] ;
00185be94: bl       #0x3f2aed0 ;
00185be98: mov      w8, #1 ;
00185be9c: strb     w8, [x21, #0x676] ;
00185bea0: cbz      x20, #0x185c0a0 ;
00185bea4: adrp     x25, #0x5300000 ;
00185bea8: ldr      x25, [x25, #0xfa8] ;
00185beac: mov      x0, x20 ;
00185beb0: ldr      x1, [x25] ;
00185beb4: bl       #0x3d473f8 ; System.Collections.Generic.List<int>$$get_Count
00185beb8: cmp      w0, #1 ;
00185bebc: b.lt     #0x185c0a0 ;
00185bec0: adrp     x8, #0x51ed000 ;
00185bec4: ldr      x8, [x8, #0xb60] ;
00185bec8: ldr      x0, [x8] ;
00185becc: ldrb     w8, [x0, #0x10a] ;
00185bed0: tbz      w8, #0, #0x185bee0 ;
00185bed4: ldr      w8, [x0, #0xbc] ;
00185bed8: cbnz     w8, #0x185bee0 ;
00185bedc: bl       #0x3f3f378 ;
00185bee0: adrp     x8, #0x51d9000 ;
00185bee4: ldr      x8, [x8, #0x618] ;
00185bee8: mov      x0, xzr ;
00185beec: ldr      x1, [x8] ;
00185bef0: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
00185bef4: mov      x21, x0 ;
00185bef8: cbnz     x21, #0x185bf00 ;
00185befc: bl       #0x3f564f0 ;
00185bf00: adrp     x8, #0x5252000 ;
00185bf04: ldr      x8, [x8, #0xae0] ;
00185bf08: mov      x0, x21 ;
00185bf0c: ldr      x1, [x8] ;
00185bf10: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
00185bf14: ldr      x1, [x25] ;
00185bf18: mov      x21, x0 ;
00185bf1c: mov      x0, x20 ;
00185bf20: bl       #0x3d473f8 ; System.Collections.Generic.List<int>$$get_Count
00185bf24: cmp      w0, #1 ;
00185bf28: b.lt     #0x185c0a0 ;
00185bf2c: adrp     x26, #0x52e6000 ;
00185bf30: adrp     x27, #0x525d000 ;
00185bf34: ldr      x26, [x26, #0x7b0] ;
00185bf38: ldr      x27, [x27, #0xb38] ;
00185bf3c: mov      w28, wzr ;
00185bf40: mov      w22, wzr ;
00185bf44: ldr      x2, [x26] ;
00185bf48: mov      x0, x20 ;
00185bf4c: mov      w1, w22 ;
00185bf50: bl       #0x3d47400 ; System.Collections.Generic.List<int>$$get_Item
00185bf54: ldr      x8, [x27] ;
00185bf58: mov      w23, w0 ;
00185bf5c: ldrb     w9, [x8, #0x10a] ;
00185bf60: tbz      w9, #0, #0x185bf74 ;
00185bf64: ldr      w9, [x8, #0xbc] ;
00185bf68: cbnz     w9, #0x185bf74 ;
00185bf6c: mov      x0, x8 ;
00185bf70: bl       #0x3f3f378 ;
00185bf74: mov      x0, xzr ;
00185bf78: mov      x1, xzr ;
00185bf7c: bl       #0x17b6608 ; ActivityRealManager$$get_Instance
00185bf80: mov      x24, x0 ;
00185bf84: cbnz     x24, #0x185bf8c ;
00185bf88: bl       #0x3f564f0 ;
00185bf8c: mov      x2, xzr ;
00185bf90: mov      x0, x24 ;
00185bf94: mov      w1, w23 ;
00185bf98: bl       #0x17b68d8 ; ActivityRealManager$$GetItem
00185bf9c: mov      x24, x0 ;
00185bfa0: cbz      x24, #0x185c03c ;
00185bfa4: ldr      w8, [x24, #0x18] ;
00185bfa8: sub      w8, w8, #0x37 ;
00185bfac: cmp      w8, #1 ;
00185bfb0: b.hi     #0x185c03c ;
00185bfb4: cbnz     x21, #0x185bfbc ;
00185bfb8: bl       #0x3f564f0 ;
00185bfbc: mov      w2, wzr ;
00185bfc0: mov      x3, xzr ;
00185bfc4: mov      x0, x21 ;
00185bfc8: mov      w1, w23 ;
00185bfcc: bl       #0x133b778 ; ActivityNoticeModule$$CheckActivityServerOpen
00185bfd0: tbz      w0, #0, #0x185c010 ;
00185bfd4: cbnz     x21, #0x185bfdc ;
00185bfd8: bl       #0x3f564f0 ;
00185bfdc: mov      w2, wzr ;
00185bfe0: mov      x3, xzr ;
00185bfe4: mov      x0, x21 ;
00185bfe8: mov      w1, w23 ;
00185bfec: bl       #0x133378c ; ActivityNoticeModule$$CheckActivityOpen
00185bff0: tbz      w0, #0, #0x185c03c ;
00185bff4: ldr      w8, [x24, #0x18] ;
00185bff8: cmp      w8, #0x37 ;
00185bffc: b.eq     #0x185c034 ;
00185c000: cmp      w8, #0x38 ;
00185c004: b.ne     #0x185c038 ;
00185c008: str      w23, [x19, #0x18] ;
00185c00c: b        #0x185c038 ;
00185c010: ldr      w8, [x24, #0x18] ;
00185c014: cmp      w8, #0x37 ;
00185c018: b.eq     #0x185c02c ;
00185c01c: cmp      w8, #0x38 ;
00185c020: b.ne     #0x185c03c ;
00185c024: str      wzr, [x19, #0x18] ;
00185c028: b        #0x185c03c ;
00185c02c: str      wzr, [x19, #0x14] ;
00185c030: b        #0x185c03c ;
00185c034: str      w23, [x19, #0x14] ;
00185c038: mov      w28, #1 ;
00185c03c: ldr      x1, [x25] ;
00185c040: mov      x0, x20 ;
00185c044: add      w22, w22, #1 ;
00185c048: bl       #0x3d473f8 ; System.Collections.Generic.List<int>$$get_Count
00185c04c: cmp      w22, w0 ;
00185c050: b.lt     #0x185bf44 ;
00185c054: tbz      w28, #0, #0x185c0a0 ;
00185c058: mov      x0, x19 ;
00185c05c: bl       #0x185acb4 ; BattlePassModule$$InitTabData
00185c060: mov      x0, x19 ;
00185c064: bl       #0x185c0bc ; BattlePassModule$$InitBattlePassGoodNeedExp
00185c068: mov      x0, x19 ;
00185c06c: bl       #0x185c4b0 ; BattlePassModule$$InitBadge
00185c070: mov      x0, x19 ;
00185c074: bl       #0x185c5a8 ; BattlePassModule$$QueryBattlePassMissionData
00185c078: mov      x0, x19 ;
00185c07c: bl       #0x185c7a0 ; BattlePassModule$$InitRelic
00185c080: mov      x0, x19 ;
00185c084: ldp      x29, x30, [sp, #0x50] ;
00185c088: ldp      x20, x19, [sp, #0x40] ;
00185c08c: ldp      x22, x21, [sp, #0x30] ;
00185c090: ldp      x24, x23, [sp, #0x20] ;
00185c094: ldp      x26, x25, [sp, #0x10] ;
00185c098: ldp      x28, x27, [sp], #0x60 ;
00185c09c: b        #0x185c8a4 ; BattlePassModule$$InitRankAward
00185c0a0: ldp      x29, x30, [sp, #0x50] ;
00185c0a4: ldp      x20, x19, [sp, #0x40] ;
00185c0a8: ldp      x22, x21, [sp, #0x30] ;
00185c0ac: ldp      x24, x23, [sp, #0x20] ;
00185c0b0: ldp      x26, x25, [sp, #0x10] ;
00185c0b4: ldp      x28, x27, [sp], #0x60 ;
00185c0b8: ret       ;
