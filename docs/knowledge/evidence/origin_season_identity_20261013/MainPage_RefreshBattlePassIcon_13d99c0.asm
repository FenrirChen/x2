; MainPage$$RefreshBattlePassIcon
; RVA [0x13d99c0,0x13d9c58), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 6413663a6e063e278580844440d1356a5747c99c7eac8bbd1dfb83fd5df32d03
0013d99c0: stp      x22, x21, [sp, #-0x30]! ;
0013d99c4: stp      x20, x19, [sp, #0x10] ;
0013d99c8: stp      x29, x30, [sp, #0x20] ;
0013d99cc: add      x29, sp, #0x20 ;
0013d99d0: adrp     x20, #0x5575000 ;
0013d99d4: ldrb     w8, [x20, #0x784] ;
0013d99d8: mov      x19, x0 ;
0013d99dc: tbnz     w8, #0, #0x13d99f8 ;
0013d99e0: adrp     x8, #0x51fe000 ;
0013d99e4: ldr      x8, [x8, #0x9f8] ;
0013d99e8: ldr      w0, [x8] ;
0013d99ec: bl       #0x3f2aed0 ;
0013d99f0: mov      w8, #1 ;
0013d99f4: strb     w8, [x20, #0x784] ;
0013d99f8: adrp     x8, #0x51ed000 ;
0013d99fc: ldr      x8, [x8, #0xb60] ;
0013d9a00: ldr      x0, [x8] ;
0013d9a04: ldrb     w8, [x0, #0x10a] ;
0013d9a08: tbz      w8, #0, #0x13d9a18 ;
0013d9a0c: ldr      w8, [x0, #0xbc] ;
0013d9a10: cbnz     w8, #0x13d9a18 ;
0013d9a14: bl       #0x3f3f378 ;
0013d9a18: adrp     x8, #0x51d9000 ;
0013d9a1c: ldr      x8, [x8, #0x618] ;
0013d9a20: mov      x0, xzr ;
0013d9a24: ldr      x1, [x8] ;
0013d9a28: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
0013d9a2c: mov      x20, x0 ;
0013d9a30: cbnz     x20, #0x13d9a38 ;
0013d9a34: bl       #0x3f564f0 ;
0013d9a38: adrp     x8, #0x5252000 ;
0013d9a3c: ldr      x8, [x8, #0xae0] ;
0013d9a40: mov      x0, x20 ;
0013d9a44: ldr      x1, [x8] ;
0013d9a48: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
0013d9a4c: mov      x20, x0 ;
0013d9a50: cbz      x20, #0x13d9a6c ;
0013d9a54: mov      x2, xzr ;
0013d9a58: mov      w1, #0x38 ;
0013d9a5c: mov      x0, x20 ;
0013d9a60: bl       #0x13284f8 ; ActivityNoticeModule$$GetOpenActivityId
0013d9a64: mov      w21, w0 ;
0013d9a68: b        #0x13d9a88 ;
0013d9a6c: bl       #0x3f564f0 ;
0013d9a70: mov      x2, xzr ;
0013d9a74: mov      w1, #0x38 ;
0013d9a78: mov      x0, x20 ;
0013d9a7c: bl       #0x13284f8 ; ActivityNoticeModule$$GetOpenActivityId
0013d9a80: mov      w21, w0 ;
0013d9a84: bl       #0x3f564f0 ;
0013d9a88: mov      x2, xzr ;
0013d9a8c: mov      x0, x20 ;
0013d9a90: mov      w1, w21 ;
0013d9a94: bl       #0x1324560 ; ActivityNoticeModule$$GetActivityData
0013d9a98: cbz      x0, #0x13d9b38 ;
0013d9a9c: mov      x1, xzr ;
0013d9aa0: bl       #0x1324668 ; ActivityInfo$$get_ActivityGroup
0013d9aa4: mov      w1, w0 ;
0013d9aa8: mov      x0, xzr ;
0013d9aac: mov      x2, xzr ;
0013d9ab0: bl       #0x18583b4 ; BattlePassModule$$GetBattlePassSeason
0013d9ab4: sub      w8, w0, #1 ;
0013d9ab8: add      w9, w0, #5 ;
0013d9abc: cmp      w8, #3 ;
0013d9ac0: csel     w8, w9, wzr, lo ;
0013d9ac4: cmp      w8, #8 ;
0013d9ac8: b.hi     #0x13d9b38 ;
0013d9acc: adrp     x9, #0x4187000 ;
0013d9ad0: add      x9, x9, #0xab0 ;
0013d9ad4: ldrsw    x8, [x9, x8, lsl #2] ;
0013d9ad8: add      x8, x8, x9 ;
0013d9adc: br       x8 ;
0013d9ae0: ldr      x20, [x19, #0x260] ;
0013d9ae4: cbnz     x20, #0x13d9aec ;
0013d9ae8: bl       #0x3f564f0 ;
0013d9aec: mov      x1, xzr ;
0013d9af0: mov      x0, x20 ;
0013d9af4: bl       #0x2d25ae4 ; UnityEngine.Component$$get_gameObject
0013d9af8: mov      x1, x0 ;
0013d9afc: mov      x0, xzr ;
0013d9b00: mov      x3, xzr ;
0013d9b04: mov      w2, #1 ;
0013d9b08: bl       #0x202f048 ; GameObjectExtion$$SetActiveSafely
0013d9b0c: ldr      x20, [x19, #0x268] ;
0013d9b10: cbnz     x20, #0x13d9b18 ;
0013d9b14: bl       #0x3f564f0 ;
0013d9b18: mov      x1, xzr ;
0013d9b1c: mov      x0, x20 ;
0013d9b20: bl       #0x2d25ae4 ; UnityEngine.Component$$get_gameObject
0013d9b24: mov      x1, x0 ;
0013d9b28: mov      x0, xzr ;
0013d9b2c: mov      w2, wzr ;
0013d9b30: mov      x3, xzr ;
0013d9b34: b        #0x13d9b9c ;
0013d9b38: ldp      x29, x30, [sp, #0x20] ;
0013d9b3c: ldp      x20, x19, [sp, #0x10] ;
0013d9b40: ldp      x22, x21, [sp], #0x30 ;
0013d9b44: ret       ;
0013d9b48: ldr      x20, [x19, #0x260] ;
0013d9b4c: cbnz     x20, #0x13d9b54 ;
0013d9b50: bl       #0x3f564f0 ;
0013d9b54: mov      x1, xzr ;
0013d9b58: mov      x0, x20 ;
0013d9b5c: bl       #0x2d25ae4 ; UnityEngine.Component$$get_gameObject
0013d9b60: mov      x1, x0 ;
0013d9b64: mov      x0, xzr ;
0013d9b68: mov      w2, wzr ;
0013d9b6c: mov      x3, xzr ;
0013d9b70: bl       #0x202f048 ; GameObjectExtion$$SetActiveSafely
0013d9b74: ldr      x20, [x19, #0x268] ;
0013d9b78: cbnz     x20, #0x13d9b80 ;
0013d9b7c: bl       #0x3f564f0 ;
0013d9b80: mov      x1, xzr ;
0013d9b84: mov      x0, x20 ;
0013d9b88: bl       #0x2d25ae4 ; UnityEngine.Component$$get_gameObject
0013d9b8c: mov      x1, x0 ;
0013d9b90: mov      x0, xzr ;
0013d9b94: mov      x3, xzr ;
0013d9b98: mov      w2, #1 ;
0013d9b9c: bl       #0x202f048 ; GameObjectExtion$$SetActiveSafely
0013d9ba0: ldr      x19, [x19, #0x270] ;
0013d9ba4: cbnz     x19, #0x13d9bac ;
0013d9ba8: bl       #0x3f564f0 ;
0013d9bac: mov      x1, xzr ;
0013d9bb0: mov      x0, x19 ;
0013d9bb4: bl       #0x2d25ae4 ; UnityEngine.Component$$get_gameObject
0013d9bb8: mov      x1, x0 ;
0013d9bbc: mov      x0, xzr ;
0013d9bc0: mov      w2, wzr ;
0013d9bc4: b        #0x13d9c44 ;
0013d9bc8: ldr      x20, [x19, #0x260] ;
0013d9bcc: cbnz     x20, #0x13d9bd4 ;
0013d9bd0: bl       #0x3f564f0 ;
0013d9bd4: mov      x1, xzr ;
0013d9bd8: mov      x0, x20 ;
0013d9bdc: bl       #0x2d25ae4 ; UnityEngine.Component$$get_gameObject
0013d9be0: mov      x1, x0 ;
0013d9be4: mov      x0, xzr ;
0013d9be8: mov      w2, wzr ;
0013d9bec: mov      x3, xzr ;
0013d9bf0: bl       #0x202f048 ; GameObjectExtion$$SetActiveSafely
0013d9bf4: ldr      x20, [x19, #0x268] ;
0013d9bf8: cbnz     x20, #0x13d9c00 ;
0013d9bfc: bl       #0x3f564f0 ;
0013d9c00: mov      x1, xzr ;
0013d9c04: mov      x0, x20 ;
0013d9c08: bl       #0x2d25ae4 ; UnityEngine.Component$$get_gameObject
0013d9c0c: mov      x1, x0 ;
0013d9c10: mov      x0, xzr ;
0013d9c14: mov      w2, wzr ;
0013d9c18: mov      x3, xzr ;
0013d9c1c: bl       #0x202f048 ; GameObjectExtion$$SetActiveSafely
0013d9c20: ldr      x19, [x19, #0x270] ;
0013d9c24: cbnz     x19, #0x13d9c2c ;
0013d9c28: bl       #0x3f564f0 ;
0013d9c2c: mov      x1, xzr ;
0013d9c30: mov      x0, x19 ;
0013d9c34: bl       #0x2d25ae4 ; UnityEngine.Component$$get_gameObject
0013d9c38: mov      x1, x0 ;
0013d9c3c: mov      x0, xzr ;
0013d9c40: mov      w2, #1 ;
0013d9c44: ldp      x29, x30, [sp, #0x20] ;
0013d9c48: ldp      x20, x19, [sp, #0x10] ;
0013d9c4c: mov      x3, xzr ;
0013d9c50: ldp      x22, x21, [sp], #0x30 ;
0013d9c54: b        #0x202f048 ; GameObjectExtion$$SetActiveSafely
