; ClientSeasonProperty$$RefreshEquip
; RVA [0x1ac6d54,0x1ac6e60), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 7c987eec0fa4e8a1cf74eb6c39b842d9f2a76ecacfc7c6faed86a5f7c5f54158
001ac6d54: stp      x22, x21, [sp, #-0x30]! ;
001ac6d58: stp      x20, x19, [sp, #0x10] ;
001ac6d5c: stp      x29, x30, [sp, #0x20] ;
001ac6d60: add      x29, sp, #0x20 ;
001ac6d64: sub      sp, sp, #0x10 ;
001ac6d68: adrp     x20, #0x5578000 ;
001ac6d6c: ldrb     w8, [x20, #0x703] ;
001ac6d70: mov      x19, x0 ;
001ac6d74: tbnz     w8, #0, #0x1ac6d90 ;
001ac6d78: adrp     x8, #0x51d7000 ;
001ac6d7c: ldr      x8, [x8, #0xbb0] ;
001ac6d80: ldr      w0, [x8] ;
001ac6d84: bl       #0x3f2aed0 ;
001ac6d88: mov      w8, #1 ;
001ac6d8c: strb     w8, [x20, #0x703] ;
001ac6d90: adrp     x8, #0x51ed000 ;
001ac6d94: ldr      x8, [x8, #0xb60] ;
001ac6d98: str      xzr, [sp, #8] ;
001ac6d9c: ldr      x0, [x8] ;
001ac6da0: ldrb     w8, [x0, #0x10a] ;
001ac6da4: tbz      w8, #0, #0x1ac6db4 ;
001ac6da8: ldr      w8, [x0, #0xbc] ;
001ac6dac: cbnz     w8, #0x1ac6db4 ;
001ac6db0: bl       #0x3f3f378 ;
001ac6db4: adrp     x8, #0x51d9000 ;
001ac6db8: ldr      x8, [x8, #0x618] ;
001ac6dbc: mov      x0, xzr ;
001ac6dc0: ldr      x1, [x8] ;
001ac6dc4: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
001ac6dc8: mov      x20, x0 ;
001ac6dcc: cbnz     x20, #0x1ac6dd4 ;
001ac6dd0: bl       #0x3f564f0 ;
001ac6dd4: adrp     x8, #0x5257000 ;
001ac6dd8: ldr      x8, [x8, #0x2e8] ;
001ac6ddc: mov      x0, x20 ;
001ac6de0: ldr      x1, [x8] ;
001ac6de4: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
001ac6de8: mov      x20, x0 ;
001ac6dec: cbnz     x20, #0x1ac6df4 ;
001ac6df0: bl       #0x3f564f0 ;
001ac6df4: ldr      x20, [x20, #0x50] ;
001ac6df8: ldr      w21, [x19, #0x28] ;
001ac6dfc: cbnz     x20, #0x1ac6e04 ;
001ac6e00: bl       #0x3f564f0 ;
001ac6e04: adrp     x8, #0x527d000 ;
001ac6e08: ldr      x8, [x8, #0x820] ;
001ac6e0c: add      x2, sp, #8 ;
001ac6e10: mov      x0, x20 ;
001ac6e14: mov      w1, w21 ;
001ac6e18: ldr      x3, [x8] ;
001ac6e1c: bl       #0x30c943c ; System.Collections.Generic.SortedList<int, object>$$TryGetValue
001ac6e20: tbz      w0, #0, #0x1ac6e4c ;
001ac6e24: mov      x0, x19 ;
001ac6e28: bl       #0x1ace300 ; ClientSeasonProperty$$RemoveEquipAttr
001ac6e2c: ldr      x20, [sp, #8] ;
001ac6e30: cbnz     x20, #0x1ac6e38 ;
001ac6e34: bl       #0x3f564f0 ;
001ac6e38: ldr      x1, [x20, #0x70] ;
001ac6e3c: mov      x0, x19 ;
001ac6e40: bl       #0x1acbae4 ; ClientSeasonProperty$$AddEqtsAttributes
001ac6e44: mov      x0, x19 ;
001ac6e48: bl       #0x1accd6c ; ClientSeasonProperty$$SetAnility
001ac6e4c: sub      sp, x29, #0x20 ;
001ac6e50: ldp      x29, x30, [sp, #0x20] ;
001ac6e54: ldp      x20, x19, [sp, #0x10] ;
001ac6e58: ldp      x22, x21, [sp], #0x30 ;
001ac6e5c: ret       ;
