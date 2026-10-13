; FavorWishModule$$OnFinishFavorWishMsg
; RVA [0x18b9f7c,0x18ba034), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 13d8e1f0b3cc1051bec74a14db45a5df0c425b426e2887311d265246b9ed9052
0018b9f7c: stp      x22, x21, [sp, #-0x30]! ;
0018b9f80: stp      x20, x19, [sp, #0x10] ;
0018b9f84: stp      x29, x30, [sp, #0x20] ;
0018b9f88: add      x29, sp, #0x20 ;
0018b9f8c: adrp     x22, #0x5577000 ;
0018b9f90: ldrb     w8, [x22, #0x909] ;
0018b9f94: mov      w20, w2 ;
0018b9f98: mov      w21, w1 ;
0018b9f9c: mov      x19, x0 ;
0018b9fa0: tbnz     w8, #0, #0x18b9fbc ;
0018b9fa4: adrp     x8, #0x5237000 ;
0018b9fa8: ldr      x8, [x8, #0x250] ;
0018b9fac: ldr      w0, [x8] ;
0018b9fb0: bl       #0x3f2aed0 ;
0018b9fb4: mov      w8, #1 ;
0018b9fb8: strb     w8, [x22, #0x909] ;
0018b9fbc: cmp      w21, #6 ;
0018b9fc0: b.ne     #0x18ba024 ;
0018b9fc4: ldr      x1, [x19, #0x18] ;
0018b9fc8: mov      w2, w20 ;
0018b9fcc: strb     wzr, [x19, #0x28] ;
0018b9fd0: bl       #0x18ba034 ; FavorWishModule$$SetTaskListPickStatus
0018b9fd4: adrp     x8, #0x5210000 ;
0018b9fd8: ldr      x8, [x8, #0xf98] ;
0018b9fdc: ldr      x0, [x8] ;
0018b9fe0: ldrb     w8, [x0, #0x10a] ;
0018b9fe4: tbz      w8, #0, #0x18b9ff4 ;
0018b9fe8: ldr      w8, [x0, #0xbc] ;
0018b9fec: cbnz     w8, #0x18b9ff4 ;
0018b9ff0: bl       #0x3f3f378 ;
0018b9ff4: adrp     x8, #0x52a7000 ;
0018b9ff8: ldr      x8, [x8, #0xd00] ;
0018b9ffc: mov      x0, xzr ;
0018ba000: mov      w1, #0xda ;
0018ba004: mov      w2, #6 ;
0018ba008: ldr      x3, [x8] ;
0018ba00c: bl       #0x221c4e4 ; CommonX2.X2EventManager$$FireEvent<int>
0018ba010: mov      x0, x19 ;
0018ba014: ldp      x29, x30, [sp, #0x20] ;
0018ba018: ldp      x20, x19, [sp, #0x10] ;
0018ba01c: ldp      x22, x21, [sp], #0x30 ;
0018ba020: b        #0x18b9d0c ; FavorWishModule$$CheckBadge
0018ba024: ldp      x29, x30, [sp, #0x20] ;
0018ba028: ldp      x20, x19, [sp, #0x10] ;
0018ba02c: ldp      x22, x21, [sp], #0x30 ;
0018ba030: ret       ;
