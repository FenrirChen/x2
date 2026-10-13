; BattlePassModule$$GetBattlePassShop
; RVA [0x1860e18,0x1860eec), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 f81f6804f109b29674a33dc36a2db6f91732fe2a26b2ca6d456ec02689521a3f
001860e18: stp      x20, x19, [sp, #-0x20]! ;
001860e1c: stp      x29, x30, [sp, #0x10] ;
001860e20: add      x29, sp, #0x10 ;
001860e24: adrp     x20, #0x5577000 ;
001860e28: ldrb     w8, [x20, #0x6a1] ;
001860e2c: mov      x19, x0 ;
001860e30: tbnz     w8, #0, #0x1860e4c ;
001860e34: adrp     x8, #0x522d000 ;
001860e38: ldr      x8, [x8, #0x778] ;
001860e3c: ldr      w0, [x8] ;
001860e40: bl       #0x3f2aed0 ;
001860e44: mov      w8, #1 ;
001860e48: strb     w8, [x20, #0x6a1] ;
001860e4c: ldr      x20, [x19, #0x120] ;
001860e50: cbnz     x20, #0x1860e78 ;
001860e54: adrp     x8, #0x5291000 ;
001860e58: ldr      x8, [x8, #0xb8] ;
001860e5c: ldr      x0, [x8] ;
001860e60: bl       #0x3f6452c ;
001860e64: mov      x1, xzr ;
001860e68: mov      x20, x0 ;
001860e6c: bl       #0x3dbcf60 ; CommandX2.C2L_ActivityShop$$.ctor
001860e70: str      x20, [x19, #0x120] ;
001860e74: cbz      x20, #0x1860ee8 ;
001860e78: mov      w8, #4 ;
001860e7c: str      w8, [x20, #0x10] ;
001860e80: adrp     x8, #0x5227000 ;
001860e84: ldr      x8, [x8, #0x168] ;
001860e88: ldr      x0, [x8] ;
001860e8c: ldrb     w8, [x0, #0x10a] ;
001860e90: tbz      w8, #0, #0x1860ea0 ;
001860e94: ldr      w8, [x0, #0xbc] ;
001860e98: cbnz     w8, #0x1860ea0 ;
001860e9c: bl       #0x3f3f378 ;
001860ea0: mov      x0, xzr ;
001860ea4: mov      x1, xzr ;
001860ea8: bl       #0x141a6c8 ; MarsNetManager$$get_Instance
001860eac: ldr      x19, [x19, #0x120] ;
001860eb0: mov      x20, x0 ;
001860eb4: cbnz     x20, #0x1860ebc ;
001860eb8: bl       #0x3f564f0 ;
001860ebc: adrp     x8, #0x51cd000 ;
001860ec0: ldr      x8, [x8, #0x460] ;
001860ec4: mov      w4, wzr ;
001860ec8: mov      w2, #3 ;
001860ecc: mov      w3, #1 ;
001860ed0: ldr      x5, [x8] ;
001860ed4: ldp      x29, x30, [sp, #0x10] ;
001860ed8: mov      x0, x20 ;
001860edc: mov      x1, x19 ;
001860ee0: ldp      x20, x19, [sp], #0x20 ;
001860ee4: b        #0x233d7ac ; MarsNetManager$$Send<C2L_ReissueDialogReciveInfo>
001860ee8: bl       #0x3f564f0 ;
