; WorldBossModule$$Tick
; RVA [0x1377424,0x1377588), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 4fcb243c4da3479fb4da3a15896aba7dda87d52fbc0deb62cb9e55ace65ae299
001377424: stp      x24, x23, [sp, #-0x40]! ;
001377428: stp      x22, x21, [sp, #0x10] ;
00137742c: stp      x20, x19, [sp, #0x20] ;
001377430: stp      x29, x30, [sp, #0x30] ;
001377434: add      x29, sp, #0x30 ;
001377438: adrp     x20, #0x5575000 ;
00137743c: ldrb     w8, [x20, #0x55b] ;
001377440: mov      x19, x0 ;
001377444: tbnz     w8, #0, #0x1377460 ;
001377448: adrp     x8, #0x51d9000 ;
00137744c: ldr      x8, [x8, #0xb60] ;
001377450: ldr      w0, [x8] ;
001377454: bl       #0x3f2aed0 ;
001377458: mov      w8, #1 ;
00137745c: strb     w8, [x20, #0x55b] ;
001377460: ldr      x21, [x19, #0x60] ;
001377464: cbz      x21, #0x137754c ;
001377468: ldr      w8, [x21, #0x30] ;
00137746c: cmp      w8, #1 ;
001377470: b.ne     #0x137754c ;
001377474: adrp     x8, #0x51ed000 ;
001377478: ldr      x8, [x8, #0xb60] ;
00137747c: ldr      x0, [x8] ;
001377480: ldrb     w8, [x0, #0x10a] ;
001377484: tbz      w8, #0, #0x1377494 ;
001377488: ldr      w8, [x0, #0xbc] ;
00137748c: cbnz     w8, #0x1377494 ;
001377490: bl       #0x3f3f378 ;
001377494: adrp     x8, #0x51d9000 ;
001377498: ldr      x8, [x8, #0x618] ;
00137749c: mov      x0, xzr ;
0013774a0: ldr      x1, [x8] ;
0013774a4: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
0013774a8: mov      x20, x0 ;
0013774ac: cbnz     x20, #0x13774b4 ;
0013774b0: bl       #0x3f564f0 ;
0013774b4: adrp     x8, #0x5262000 ;
0013774b8: ldr      x8, [x8, #0xdb8] ;
0013774bc: mov      x0, x20 ;
0013774c0: ldr      x1, [x8] ;
0013774c4: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
0013774c8: ldr      x8, [x21, #0x38] ;
0013774cc: mov      x9, #0x20c4000000000000 ;
0013774d0: movk     x9, #0x9ba5, lsl #32 ;
0013774d4: movk     x9, #0xe353, lsl #16 ;
0013774d8: movk     x9, #0xf7cf ;
0013774dc: mov      x20, x0 ;
0013774e0: smulh    x22, x8, x9 ;
0013774e4: cbnz     x20, #0x13774ec ;
0013774e8: bl       #0x3f564f0 ;
0013774ec: mov      x1, xzr ;
0013774f0: mov      x0, x20 ;
0013774f4: asr      x23, x22, #7 ;
0013774f8: bl       #0x17884c8 ; ServerTimeModule$$get_ServerTime
0013774fc: mov      x20, x0 ;
001377500: cbnz     x20, #0x1377508 ;
001377504: bl       #0x3f564f0 ;
001377508: mov      x1, xzr ;
00137750c: mov      x0, x20 ;
001377510: add      x22, x23, x22, lsr #63 ;
001377514: bl       #0x3e51634 ; ServerTime$$GetCurTimeSecFrom1970
001377518: ldr      x8, [x19, #0x118] ;
00137751c: mov      x20, x0 ;
001377520: cbz      x8, #0x137753c ;
001377524: adrp     x9, #0x5301000 ;
001377528: ldr      x9, [x9, #0x388] ;
00137752c: sub      w1, w22, w20 ;
001377530: mov      x0, x8 ;
001377534: ldr      x2, [x9] ;
001377538: bl       #0x2621a2c ; System.Action<int>$$Invoke
00137753c: cmp      x22, x20 ;
001377540: b.le     #0x1377554 ;
001377544: mov      w0, #1 ;
001377548: b        #0x1377574 ;
00137754c: mov      w0, wzr ;
001377550: b        #0x1377574 ;
001377554: ldr      x1, [x21, #0x10] ;
001377558: ldr      x2, [x21, #0x20] ;
00137755c: mov      w3, wzr ;
001377560: mov      w4, #1 ;
001377564: mov      x0, x19 ;
001377568: bl       #0x136f0a4 ; WorldBossModule$$QueryBossData
00137756c: mov      w0, wzr ;
001377570: str      wzr, [x19, #0x110] ;
001377574: ldp      x29, x30, [sp, #0x30] ;
001377578: ldp      x20, x19, [sp, #0x20] ;
00137757c: ldp      x22, x21, [sp, #0x10] ;
001377580: ldp      x24, x23, [sp], #0x40 ;
001377584: ret       ;
