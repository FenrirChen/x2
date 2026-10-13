; ShopModule$$QueryShopData
; RVA [0x17a7a58,0x17a7b10), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 d3275698d161f5286e84daf2b1d74df18f7842f7b2060a5ff6497d4ee9e80a1d
0017a7a58: stp      x22, x21, [sp, #-0x30]! ;
0017a7a5c: stp      x20, x19, [sp, #0x10] ;
0017a7a60: stp      x29, x30, [sp, #0x20] ;
0017a7a64: add      x29, sp, #0x20 ;
0017a7a68: adrp     x21, #0x5577000 ;
0017a7a6c: ldrb     w8, [x21, #0x1a8] ;
0017a7a70: mov      w20, w1 ;
0017a7a74: mov      x19, x0 ;
0017a7a78: tbnz     w8, #0, #0x17a7a94 ;
0017a7a7c: adrp     x8, #0x52d3000 ;
0017a7a80: ldr      x8, [x8, #0x5f8] ;
0017a7a84: ldr      w0, [x8] ;
0017a7a88: bl       #0x3f2aed0 ;
0017a7a8c: mov      w8, #1 ;
0017a7a90: strb     w8, [x21, #0x1a8] ;
0017a7a94: ldr      x21, [x19, #0xa0] ;
0017a7a98: cbnz     x21, #0x17a7aa0 ;
0017a7a9c: bl       #0x3f564f0 ;
0017a7aa0: str      w20, [x21, #0x10] ;
0017a7aa4: adrp     x8, #0x5227000 ;
0017a7aa8: ldr      x8, [x8, #0x168] ;
0017a7aac: ldr      x0, [x8] ;
0017a7ab0: ldrb     w8, [x0, #0x10a] ;
0017a7ab4: tbz      w8, #0, #0x17a7ac4 ;
0017a7ab8: ldr      w8, [x0, #0xbc] ;
0017a7abc: cbnz     w8, #0x17a7ac4 ;
0017a7ac0: bl       #0x3f3f378 ;
0017a7ac4: mov      x0, xzr ;
0017a7ac8: mov      x1, xzr ;
0017a7acc: bl       #0x141a6c8 ; MarsNetManager$$get_Instance
0017a7ad0: ldr      x19, [x19, #0xa0] ;
0017a7ad4: mov      x20, x0 ;
0017a7ad8: cbnz     x20, #0x17a7ae0 ;
0017a7adc: bl       #0x3f564f0 ;
0017a7ae0: adrp     x8, #0x51cd000 ;
0017a7ae4: ldr      x8, [x8, #0x460] ;
0017a7ae8: mov      x0, x20 ;
0017a7aec: mov      x1, x19 ;
0017a7af0: mov      w4, wzr ;
0017a7af4: ldr      x5, [x8] ;
0017a7af8: ldp      x29, x30, [sp, #0x20] ;
0017a7afc: ldp      x20, x19, [sp, #0x10] ;
0017a7b00: mov      w2, #3 ;
0017a7b04: mov      w3, #1 ;
0017a7b08: ldp      x22, x21, [sp], #0x30 ;
0017a7b0c: b        #0x233d7ac ; MarsNetManager$$Send<C2L_ReissueDialogReciveInfo>
