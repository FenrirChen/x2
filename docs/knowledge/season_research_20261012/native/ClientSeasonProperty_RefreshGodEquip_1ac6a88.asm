; ClientSeasonProperty$$RefreshGodEquip
; RVA [0x1ac6a88,0x1ac6b94), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 2342213d6b7b176da6c0973535c1203f0a00e7d419947935ef1005c987cef81b
001ac6a88: stp      x22, x21, [sp, #-0x30]! ;
001ac6a8c: stp      x20, x19, [sp, #0x10] ;
001ac6a90: stp      x29, x30, [sp, #0x20] ;
001ac6a94: add      x29, sp, #0x20 ;
001ac6a98: sub      sp, sp, #0x10 ;
001ac6a9c: adrp     x20, #0x5578000 ;
001ac6aa0: ldrb     w8, [x20, #0x704] ;
001ac6aa4: mov      x19, x0 ;
001ac6aa8: tbnz     w8, #0, #0x1ac6ac4 ;
001ac6aac: adrp     x8, #0x523a000 ;
001ac6ab0: ldr      x8, [x8, #0xde8] ;
001ac6ab4: ldr      w0, [x8] ;
001ac6ab8: bl       #0x3f2aed0 ;
001ac6abc: mov      w8, #1 ;
001ac6ac0: strb     w8, [x20, #0x704] ;
001ac6ac4: adrp     x8, #0x51ed000 ;
001ac6ac8: ldr      x8, [x8, #0xb60] ;
001ac6acc: str      xzr, [sp, #8] ;
001ac6ad0: ldr      x0, [x8] ;
001ac6ad4: ldrb     w8, [x0, #0x10a] ;
001ac6ad8: tbz      w8, #0, #0x1ac6ae8 ;
001ac6adc: ldr      w8, [x0, #0xbc] ;
001ac6ae0: cbnz     w8, #0x1ac6ae8 ;
001ac6ae4: bl       #0x3f3f378 ;
001ac6ae8: adrp     x8, #0x51d9000 ;
001ac6aec: ldr      x8, [x8, #0x618] ;
001ac6af0: mov      x0, xzr ;
001ac6af4: ldr      x1, [x8] ;
001ac6af8: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
001ac6afc: mov      x20, x0 ;
001ac6b00: cbnz     x20, #0x1ac6b08 ;
001ac6b04: bl       #0x3f564f0 ;
001ac6b08: adrp     x8, #0x5257000 ;
001ac6b0c: ldr      x8, [x8, #0x2e8] ;
001ac6b10: mov      x0, x20 ;
001ac6b14: ldr      x1, [x8] ;
001ac6b18: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
001ac6b1c: mov      x20, x0 ;
001ac6b20: cbnz     x20, #0x1ac6b28 ;
001ac6b24: bl       #0x3f564f0 ;
001ac6b28: ldr      x20, [x20, #0x50] ;
001ac6b2c: ldr      w21, [x19, #0x28] ;
001ac6b30: cbnz     x20, #0x1ac6b38 ;
001ac6b34: bl       #0x3f564f0 ;
001ac6b38: adrp     x8, #0x527d000 ;
001ac6b3c: ldr      x8, [x8, #0x820] ;
001ac6b40: add      x2, sp, #8 ;
001ac6b44: mov      x0, x20 ;
001ac6b48: mov      w1, w21 ;
001ac6b4c: ldr      x3, [x8] ;
001ac6b50: bl       #0x30c943c ; System.Collections.Generic.SortedList<int, object>$$TryGetValue
001ac6b54: tbz      w0, #0, #0x1ac6b80 ;
001ac6b58: mov      x0, x19 ;
001ac6b5c: bl       #0x1ace5fc ; ClientSeasonProperty$$RemoveGodEquipAttr
001ac6b60: ldr      x20, [sp, #8] ;
001ac6b64: cbnz     x20, #0x1ac6b6c ;
001ac6b68: bl       #0x3f564f0 ;
001ac6b6c: ldr      x1, [x20, #0x20] ;
001ac6b70: mov      x0, x19 ;
001ac6b74: bl       #0x1acc2b4 ; ClientSeasonProperty$$AddHeroGodEquipAttributes
001ac6b78: mov      x0, x19 ;
001ac6b7c: bl       #0x1accd6c ; ClientSeasonProperty$$SetAnility
001ac6b80: sub      sp, x29, #0x20 ;
001ac6b84: ldp      x29, x30, [sp, #0x20] ;
001ac6b88: ldp      x20, x19, [sp, #0x10] ;
001ac6b8c: ldp      x22, x21, [sp], #0x30 ;
001ac6b90: ret       ;
