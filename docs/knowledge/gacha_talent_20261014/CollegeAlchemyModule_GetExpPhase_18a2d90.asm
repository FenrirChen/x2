; CollegeAlchemyModule$$GetExpPhase
; RVA [0x18a2d90,0x18a2f88), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 5c5203934c1ef94c90921b7925c0f00fab46b42d73ee478a64ee6b697c1bd821
0018a2d90: stp      x28, x27, [sp, #-0x60]! ;
0018a2d94: stp      x26, x25, [sp, #0x10] ;
0018a2d98: stp      x24, x23, [sp, #0x20] ;
0018a2d9c: stp      x22, x21, [sp, #0x30] ;
0018a2da0: stp      x20, x19, [sp, #0x40] ;
0018a2da4: stp      x29, x30, [sp, #0x50] ;
0018a2da8: add      x29, sp, #0x50 ;
0018a2dac: adrp     x24, #0x5577000 ;
0018a2db0: ldrb     w8, [x24, #0x891] ;
0018a2db4: mov      x19, x4 ;
0018a2db8: mov      x21, x3 ;
0018a2dbc: mov      x20, x2 ;
0018a2dc0: mov      w22, w1 ;
0018a2dc4: mov      x23, x0 ;
0018a2dc8: tbnz     w8, #0, #0x18a2de4 ;
0018a2dcc: adrp     x8, #0x5257000 ;
0018a2dd0: ldr      x8, [x8, #0x90] ;
0018a2dd4: ldr      w0, [x8] ;
0018a2dd8: bl       #0x3f2aed0 ;
0018a2ddc: mov      w8, #1 ;
0018a2de0: strb     w8, [x24, #0x891] ;
0018a2de4: mov      w8, #-1 ;
0018a2de8: str      w8, [x20] ;
0018a2dec: str      wzr, [x21] ;
0018a2df0: str      wzr, [x19] ;
0018a2df4: adrp     x8, #0x52a9000 ;
0018a2df8: ldr      x8, [x8, #0xe08] ;
0018a2dfc: ldr      x0, [x8] ;
0018a2e00: ldrb     w8, [x0, #0x10a] ;
0018a2e04: tbz      w8, #0, #0x18a2e14 ;
0018a2e08: ldr      w8, [x0, #0xbc] ;
0018a2e0c: cbnz     w8, #0x18a2e14 ;
0018a2e10: bl       #0x3f3f378 ;
0018a2e14: mov      x0, xzr ;
0018a2e18: mov      x1, xzr ;
0018a2e1c: bl       #0x1956bf4 ; CollegeRecipeManager$$get_Instance
0018a2e20: mov      x24, x0 ;
0018a2e24: cbnz     x24, #0x18a2e2c ;
0018a2e28: bl       #0x3f564f0 ;
0018a2e2c: mov      x2, xzr ;
0018a2e30: mov      x0, x24 ;
0018a2e34: mov      w1, w22 ;
0018a2e38: bl       #0x1956ec4 ; CollegeRecipeManager$$GetItem
0018a2e3c: mov      x24, x0 ;
0018a2e40: cbz      x24, #0x18a2f6c ;
0018a2e44: ldr      x0, [x24, #0x48] ;
0018a2e48: cbz      x0, #0x18a2f6c ;
0018a2e4c: adrp     x27, #0x5300000 ;
0018a2e50: ldr      x27, [x27, #0xfa8] ;
0018a2e54: ldr      x1, [x27] ;
0018a2e58: bl       #0x3d473f8 ; System.Collections.Generic.List<int>$$get_Count
0018a2e5c: cbz      w0, #0x18a2f6c ;
0018a2e60: ldr      x25, [x24, #0x48] ;
0018a2e64: cbnz     x25, #0x18a2e6c ;
0018a2e68: bl       #0x3f564f0 ;
0018a2e6c: adrp     x26, #0x52e6000 ;
0018a2e70: ldr      x26, [x26, #0x7b0] ;
0018a2e74: mov      w1, wzr ;
0018a2e78: mov      x0, x25 ;
0018a2e7c: ldr      x2, [x26] ;
0018a2e80: bl       #0x3d47400 ; System.Collections.Generic.List<int>$$get_Item
0018a2e84: str      w0, [x19] ;
0018a2e88: ldr      x23, [x23, #0x40] ;
0018a2e8c: cbnz     x23, #0x18a2e94 ;
0018a2e90: bl       #0x3f564f0 ;
0018a2e94: adrp     x8, #0x5218000 ;
0018a2e98: ldr      x8, [x8, #0xea0] ;
0018a2e9c: mov      x0, x23 ;
0018a2ea0: mov      w1, w22 ;
0018a2ea4: mov      x2, x21 ;
0018a2ea8: ldr      x3, [x8] ;
0018a2eac: bl       #0x3609a64 ; System.Collections.Generic.Dictionary<int, int>$$TryGetValue
0018a2eb0: tbz      w0, #0, #0x18a2f6c ;
0018a2eb4: ldr      x22, [x24, #0x48] ;
0018a2eb8: cbnz     x22, #0x18a2ec0 ;
0018a2ebc: bl       #0x3f564f0 ;
0018a2ec0: ldr      x1, [x27] ;
0018a2ec4: mov      x0, x22 ;
0018a2ec8: bl       #0x3d473f8 ; System.Collections.Generic.List<int>$$get_Count
0018a2ecc: mov      w23, w0 ;
0018a2ed0: mov      w24, wzr ;
0018a2ed4: b        #0x18a2edc ;
0018a2ed8: add      w24, w24, #1 ;
0018a2edc: cbnz     x22, #0x18a2ee4 ;
0018a2ee0: bl       #0x3f564f0 ;
0018a2ee4: cmp      w24, w23 ;
0018a2ee8: b.ge     #0x18a2f10 ;
0018a2eec: ldr      x2, [x26] ;
0018a2ef0: mov      x0, x22 ;
0018a2ef4: mov      w1, w24 ;
0018a2ef8: bl       #0x3d47400 ; System.Collections.Generic.List<int>$$get_Item
0018a2efc: ldr      w8, [x21] ;
0018a2f00: cmp      w8, w0 ;
0018a2f04: b.ge     #0x18a2ed8 ;
0018a2f08: str      w24, [x20] ;
0018a2f0c: b        #0x18a2f68 ;
0018a2f10: ldr      x1, [x27] ;
0018a2f14: mov      x0, x22 ;
0018a2f18: bl       #0x3d473f8 ; System.Collections.Generic.List<int>$$get_Count
0018a2f1c: sub      w1, w0, #1 ;
0018a2f20: str      w1, [x20] ;
0018a2f24: cbz      x22, #0x18a2f3c ;
0018a2f28: ldr      x2, [x26] ;
0018a2f2c: mov      x0, x22 ;
0018a2f30: bl       #0x3d47400 ; System.Collections.Generic.List<int>$$get_Item
0018a2f34: str      w0, [x21] ;
0018a2f38: b        #0x18a2f58 ;
0018a2f3c: bl       #0x3f564f0 ;
0018a2f40: ldr      w1, [x20] ;
0018a2f44: ldr      x2, [x26] ;
0018a2f48: mov      x0, xzr ;
0018a2f4c: bl       #0x3d47400 ; System.Collections.Generic.List<int>$$get_Item
0018a2f50: str      w0, [x21] ;
0018a2f54: bl       #0x3f564f0 ;
0018a2f58: ldr      w1, [x20] ;
0018a2f5c: ldr      x2, [x26] ;
0018a2f60: mov      x0, x22 ;
0018a2f64: bl       #0x3d47400 ; System.Collections.Generic.List<int>$$get_Item
0018a2f68: str      w0, [x19] ;
0018a2f6c: ldp      x29, x30, [sp, #0x50] ;
0018a2f70: ldp      x20, x19, [sp, #0x40] ;
0018a2f74: ldp      x22, x21, [sp, #0x30] ;
0018a2f78: ldp      x24, x23, [sp, #0x20] ;
0018a2f7c: ldp      x26, x25, [sp, #0x10] ;
0018a2f80: ldp      x28, x27, [sp], #0x60 ;
0018a2f84: ret       ;
