; ServerTime$$GetServerDateTime
; RVA [0x3e51344,0x3e513d0), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 2c173a1fb32fed99b62f449eea70403082b1650a705ead2d9508ab9e312191af
003e51344: stp      x20, x19, [sp, #-0x20]! ;
003e51348: stp      x29, x30, [sp, #0x10] ;
003e5134c: add      x29, sp, #0x10 ;
003e51350: sub      sp, sp, #0x10 ;
003e51354: adrp     x20, #0x558b000 ;
003e51358: ldrb     w8, [x20, #0xf61] ;
003e5135c: mov      x19, x1 ;
003e51360: tbnz     w8, #0, #0x3e5137c ;
003e51364: adrp     x8, #0x52a1000 ;
003e51368: ldr      x8, [x8, #0xb00] ;
003e5136c: ldr      w0, [x8] ;
003e51370: bl       #0x3f2aed0 ;
003e51374: mov      w8, #1 ;
003e51378: strb     w8, [x20, #0xf61] ;
003e5137c: adrp     x20, #0x51ee000 ;
003e51380: ldr      x20, [x20, #0xdb8] ;
003e51384: ldr      x0, [x20] ;
003e51388: stp      xzr, xzr, [sp] ;
003e5138c: ldrb     w8, [x0, #0x10a] ;
003e51390: tbz      w8, #0, #0x3e513a4 ;
003e51394: ldr      w8, [x0, #0xbc] ;
003e51398: cbnz     w8, #0x3e513a4 ;
003e5139c: bl       #0x3f3f378 ;
003e513a0: ldr      x0, [x20] ;
003e513a4: ldr      x8, [x0, #0xa0] ;
003e513a8: scvtf    d0, x19 ;
003e513ac: mov      x1, xzr ;
003e513b0: mov      x0, sp ;
003e513b4: ldp      x9, x8, [x8] ;
003e513b8: stp      x9, x8, [sp] ;
003e513bc: bl       #0x2e15424 ;
003e513c0: sub      sp, x29, #0x10 ;
003e513c4: ldp      x29, x30, [sp, #0x10] ;
003e513c8: ldp      x20, x19, [sp], #0x20 ;
003e513cc: ret       ;
