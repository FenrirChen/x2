; BattlePassModule$$InitChallengeSection
; RVA [0x185b7b4,0x185b9a8), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 0ea741c251d4567511b070c4c1fef201430d403376e3e67390537c6314ac50f0
00185b7b4: stp      x28, x27, [sp, #-0x60]! ;
00185b7b8: stp      x26, x25, [sp, #0x10] ;
00185b7bc: stp      x24, x23, [sp, #0x20] ;
00185b7c0: stp      x22, x21, [sp, #0x30] ;
00185b7c4: stp      x20, x19, [sp, #0x40] ;
00185b7c8: stp      x29, x30, [sp, #0x50] ;
00185b7cc: add      x29, sp, #0x50 ;
00185b7d0: adrp     x20, #0x5577000 ;
00185b7d4: ldrb     w8, [x20, #0x6c8] ;
00185b7d8: mov      x19, x0 ;
00185b7dc: tbnz     w8, #0, #0x185b7f8 ;
00185b7e0: adrp     x8, #0x51f6000 ;
00185b7e4: ldr      x8, [x8, #0x58] ;
00185b7e8: ldr      w0, [x8] ;
00185b7ec: bl       #0x3f2aed0 ;
00185b7f0: mov      w8, #1 ;
00185b7f4: strb     w8, [x20, #0x6c8] ;
00185b7f8: ldr      x20, [x19, #0x198] ;
00185b7fc: cbnz     x20, #0x185b804 ;
00185b800: bl       #0x3f564f0 ;
00185b804: adrp     x8, #0x52b0000 ;
00185b808: ldr      x8, [x8, #0xfe8] ;
00185b80c: mov      x0, x20 ;
00185b810: ldr      x1, [x8] ;
00185b814: bl       #0x3d456dc ; System.Collections.Generic.List<int>$$Clear
00185b818: adrp     x8, #0x52ed000 ;
00185b81c: ldr      x8, [x8, #0xaf8] ;
00185b820: ldr      x0, [x8] ;
00185b824: ldrb     w8, [x0, #0x10a] ;
00185b828: tbz      w8, #0, #0x185b838 ;
00185b82c: ldr      w8, [x0, #0xbc] ;
00185b830: cbnz     w8, #0x185b838 ;
00185b834: bl       #0x3f3f378 ;
00185b838: mov      x0, xzr ;
00185b83c: mov      x1, xzr ;
00185b840: bl       #0x1bde94c ; SeasonConfigManager$$get_Instance
00185b844: mov      x20, x0 ;
00185b848: cbnz     x20, #0x185b850 ;
00185b84c: bl       #0x3f564f0 ;
00185b850: mov      x1, xzr ;
00185b854: mov      x0, x20 ;
00185b858: bl       #0x1bded24 ; SeasonConfigManager$$GetAllItem
00185b85c: mov      x21, x0 ;
00185b860: cbnz     x21, #0x185b868 ;
00185b864: bl       #0x3f564f0 ;
00185b868: adrp     x24, #0x52f6000 ;
00185b86c: adrp     x25, #0x5230000 ;
00185b870: adrp     x26, #0x5300000 ;
00185b874: adrp     x27, #0x52e6000 ;
00185b878: adrp     x28, #0x52e8000 ;
00185b87c: ldr      x21, [x21, #0x18] ;
00185b880: ldr      x24, [x24, #0x678] ;
00185b884: ldr      x25, [x25, #0xc08] ;
00185b888: ldr      x26, [x26, #0xfa8] ;
00185b88c: ldr      x27, [x27, #0x7b0] ;
00185b890: ldr      x28, [x28, #0x88] ;
00185b894: mov      w20, wzr ;
00185b898: b        #0x185b8a0 ;
00185b89c: add      w20, w20, #1 ;
00185b8a0: cbnz     x21, #0x185b8a8 ;
00185b8a4: bl       #0x3f564f0 ;
00185b8a8: ldr      x1, [x24] ;
00185b8ac: mov      x0, x21 ;
00185b8b0: bl       #0x3d51884 ; System.Collections.Generic.List<IEventSystemHandler>$$get_Count
00185b8b4: cmp      w20, w0 ;
00185b8b8: b.ge     #0x185b98c ;
00185b8bc: cbnz     x21, #0x185b8c4 ;
00185b8c0: bl       #0x3f564f0 ;
00185b8c4: ldr      x2, [x25] ;
00185b8c8: mov      x0, x21 ;
00185b8cc: mov      w1, w20 ;
00185b8d0: bl       #0x3d5188c ; System.Collections.Generic.List<IEventSystemHandler>$$get_Item
00185b8d4: mov      x22, x0 ;
00185b8d8: cbnz     x22, #0x185b8e0 ;
00185b8dc: bl       #0x3f564f0 ;
00185b8e0: ldr      x23, [x22, #0x20] ;
00185b8e4: cbnz     x23, #0x185b8ec ;
00185b8e8: bl       #0x3f564f0 ;
00185b8ec: ldr      x1, [x26] ;
00185b8f0: mov      x0, x23 ;
00185b8f4: bl       #0x3d473f8 ; System.Collections.Generic.List<int>$$get_Count
00185b8f8: cmp      w0, #1 ;
00185b8fc: b.lt     #0x185b89c ;
00185b900: cbnz     x22, #0x185b908 ;
00185b904: bl       #0x3f564f0 ;
00185b908: ldr      x23, [x22, #0x20] ;
00185b90c: cbnz     x23, #0x185b914 ;
00185b910: bl       #0x3f564f0 ;
00185b914: ldr      x2, [x27] ;
00185b918: mov      w1, wzr ;
00185b91c: mov      x0, x23 ;
00185b920: bl       #0x3d47400 ; System.Collections.Generic.List<int>$$get_Item
00185b924: ldr      w8, [x19, #0x14] ;
00185b928: cmp      w0, w8 ;
00185b92c: b.ne     #0x185b89c ;
00185b930: cbnz     x22, #0x185b938 ;
00185b934: bl       #0x3f564f0 ;
00185b938: ldr      w8, [x22, #0x14] ;
00185b93c: cmp      w8, #1 ;
00185b940: b.ne     #0x185b89c ;
00185b944: ldr      x22, [x19, #0x198] ;
00185b948: cbnz     x21, #0x185b950 ;
00185b94c: bl       #0x3f564f0 ;
00185b950: ldr      x2, [x25] ;
00185b954: mov      x0, x21 ;
00185b958: mov      w1, w20 ;
00185b95c: bl       #0x3d5188c ; System.Collections.Generic.List<IEventSystemHandler>$$get_Item
00185b960: mov      x23, x0 ;
00185b964: cbnz     x23, #0x185b96c ;
00185b968: bl       #0x3f564f0 ;
00185b96c: ldr      w23, [x23, #0x10] ;
00185b970: cbnz     x22, #0x185b978 ;
00185b974: bl       #0x3f564f0 ;
00185b978: ldr      x2, [x28] ;
00185b97c: mov      x0, x22 ;
00185b980: mov      w1, w23 ;
00185b984: bl       #0x3d44f2c ; System.Collections.Generic.List<int>$$Add
00185b988: b        #0x185b89c ;
00185b98c: ldp      x29, x30, [sp, #0x50] ;
00185b990: ldp      x20, x19, [sp, #0x40] ;
00185b994: ldp      x22, x21, [sp, #0x30] ;
00185b998: ldp      x24, x23, [sp, #0x20] ;
00185b99c: ldp      x26, x25, [sp, #0x10] ;
00185b9a0: ldp      x28, x27, [sp], #0x60 ;
00185b9a4: ret       ;
