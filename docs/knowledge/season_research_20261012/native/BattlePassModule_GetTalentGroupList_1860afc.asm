; BattlePassModule$$GetTalentGroupList
; RVA [0x1860afc,0x1860c88), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 c210f0460dcc429260f566688a0ed45f76db3dbfa869a47bda835fb3a98401c7
001860afc: stp      x26, x25, [sp, #-0x50]! ;
001860b00: stp      x24, x23, [sp, #0x10] ;
001860b04: stp      x22, x21, [sp, #0x20] ;
001860b08: stp      x20, x19, [sp, #0x30] ;
001860b0c: stp      x29, x30, [sp, #0x40] ;
001860b10: add      x29, sp, #0x40 ;
001860b14: adrp     x20, #0x5577000 ;
001860b18: ldrb     w8, [x20, #0x69e] ;
001860b1c: mov      x19, x0 ;
001860b20: tbnz     w8, #0, #0x1860b3c ;
001860b24: adrp     x8, #0x5234000 ;
001860b28: ldr      x8, [x8, #0x178] ;
001860b2c: ldr      w0, [x8] ;
001860b30: bl       #0x3f2aed0 ;
001860b34: mov      w8, #1 ;
001860b38: strb     w8, [x20, #0x69e] ;
001860b3c: ldr      x20, [x19, #0x118] ;
001860b40: cbnz     x20, #0x1860b48 ;
001860b44: bl       #0x3f564f0 ;
001860b48: adrp     x8, #0x52b0000 ;
001860b4c: ldr      x8, [x8, #0xfe8] ;
001860b50: mov      x0, x20 ;
001860b54: ldr      x1, [x8] ;
001860b58: bl       #0x3d456dc ; System.Collections.Generic.List<int>$$Clear
001860b5c: adrp     x8, #0x52bf000 ;
001860b60: ldr      x8, [x8, #0x168] ;
001860b64: ldr      x0, [x8] ;
001860b68: ldrb     w8, [x0, #0x10a] ;
001860b6c: tbz      w8, #0, #0x1860b7c ;
001860b70: ldr      w8, [x0, #0xbc] ;
001860b74: cbnz     w8, #0x1860b7c ;
001860b78: bl       #0x3f3f378 ;
001860b7c: mov      x0, xzr ;
001860b80: mov      x1, xzr ;
001860b84: bl       #0x14c21cc ; BattlepassTalentGroupManager$$get_Instance
001860b88: mov      x20, x0 ;
001860b8c: cbnz     x20, #0x1860b94 ;
001860b90: bl       #0x3f564f0 ;
001860b94: mov      x1, xzr ;
001860b98: mov      x0, x20 ;
001860b9c: bl       #0x14c25a4 ; BattlepassTalentGroupManager$$GetAllItem
001860ba0: mov      x21, x0 ;
001860ba4: cbnz     x21, #0x1860bac ;
001860ba8: bl       #0x3f564f0 ;
001860bac: adrp     x24, #0x5284000 ;
001860bb0: adrp     x25, #0x5234000 ;
001860bb4: adrp     x26, #0x52e8000 ;
001860bb8: ldr      x21, [x21, #0x18] ;
001860bbc: ldr      x24, [x24, #0xd30] ;
001860bc0: ldr      x25, [x25, #0x1c0] ;
001860bc4: ldr      x26, [x26, #0x88] ;
001860bc8: mov      w20, wzr ;
001860bcc: b        #0x1860bd4 ;
001860bd0: add      w20, w20, #1 ;
001860bd4: cbnz     x21, #0x1860bdc ;
001860bd8: bl       #0x3f564f0 ;
001860bdc: ldr      x1, [x24] ;
001860be0: mov      x0, x21 ;
001860be4: bl       #0x3d51884 ; System.Collections.Generic.List<IEventSystemHandler>$$get_Count
001860be8: cmp      w20, w0 ;
001860bec: b.ge     #0x1860c6c ;
001860bf0: cbnz     x21, #0x1860bf8 ;
001860bf4: bl       #0x3f564f0 ;
001860bf8: ldr      x2, [x25] ;
001860bfc: mov      x0, x21 ;
001860c00: mov      w1, w20 ;
001860c04: bl       #0x3d5188c ; System.Collections.Generic.List<IEventSystemHandler>$$get_Item
001860c08: mov      x22, x0 ;
001860c0c: cbnz     x22, #0x1860c14 ;
001860c10: bl       #0x3f564f0 ;
001860c14: ldr      w8, [x22, #0x18] ;
001860c18: ldr      w9, [x19, #0x14] ;
001860c1c: cmp      w8, w9 ;
001860c20: b.ne     #0x1860bd0 ;
001860c24: ldr      x22, [x19, #0x118] ;
001860c28: cbnz     x21, #0x1860c30 ;
001860c2c: bl       #0x3f564f0 ;
001860c30: ldr      x2, [x25] ;
001860c34: mov      x0, x21 ;
001860c38: mov      w1, w20 ;
001860c3c: bl       #0x3d5188c ; System.Collections.Generic.List<IEventSystemHandler>$$get_Item
001860c40: mov      x23, x0 ;
001860c44: cbnz     x23, #0x1860c4c ;
001860c48: bl       #0x3f564f0 ;
001860c4c: ldr      w23, [x23, #0x10] ;
001860c50: cbnz     x22, #0x1860c58 ;
001860c54: bl       #0x3f564f0 ;
001860c58: ldr      x2, [x26] ;
001860c5c: mov      x0, x22 ;
001860c60: mov      w1, w23 ;
001860c64: bl       #0x3d44f2c ; System.Collections.Generic.List<int>$$Add
001860c68: b        #0x1860bd0 ;
001860c6c: ldr      x0, [x19, #0x118] ;
001860c70: ldp      x29, x30, [sp, #0x40] ;
001860c74: ldp      x20, x19, [sp, #0x30] ;
001860c78: ldp      x22, x21, [sp, #0x20] ;
001860c7c: ldp      x24, x23, [sp, #0x10] ;
001860c80: ldp      x26, x25, [sp], #0x50 ;
001860c84: ret       ;
