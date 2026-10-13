; BattlePassModule$$CheckBattlePassCanBuy
; RVA [0x185f8fc,0x185f9dc), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 266f5fd93725be866185928a25785766e38b58533bb512dfd91dbaf392a5be44
00185f8fc: stp      x20, x19, [sp, #-0x20]! ;
00185f900: stp      x29, x30, [sp, #0x10] ;
00185f904: add      x29, sp, #0x10 ;
00185f908: adrp     x20, #0x5577000 ;
00185f90c: ldrb     w8, [x20, #0x694] ;
00185f910: mov      x19, x0 ;
00185f914: tbnz     w8, #0, #0x185f930 ;
00185f918: adrp     x8, #0x5217000 ;
00185f91c: ldr      x8, [x8, #0xda0] ;
00185f920: ldr      w0, [x8] ;
00185f924: bl       #0x3f2aed0 ;
00185f928: mov      w8, #1 ;
00185f92c: strb     w8, [x20, #0x694] ;
00185f930: adrp     x8, #0x51ed000 ;
00185f934: ldr      x8, [x8, #0xb60] ;
00185f938: ldr      x0, [x8] ;
00185f93c: ldrb     w8, [x0, #0x10a] ;
00185f940: tbz      w8, #0, #0x185f950 ;
00185f944: ldr      w8, [x0, #0xbc] ;
00185f948: cbnz     w8, #0x185f950 ;
00185f94c: bl       #0x3f3f378 ;
00185f950: adrp     x8, #0x51d9000 ;
00185f954: ldr      x8, [x8, #0x618] ;
00185f958: mov      x0, xzr ;
00185f95c: ldr      x1, [x8] ;
00185f960: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
00185f964: mov      x20, x0 ;
00185f968: cbnz     x20, #0x185f970 ;
00185f96c: bl       #0x3f564f0 ;
00185f970: adrp     x8, #0x5262000 ;
00185f974: ldr      x8, [x8, #0xdb8] ;
00185f978: mov      x0, x20 ;
00185f97c: ldr      x1, [x8] ;
00185f980: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
00185f984: mov      x20, x0 ;
00185f988: cbnz     x20, #0x185f990 ;
00185f98c: bl       #0x3f564f0 ;
00185f990: mov      x1, xzr ;
00185f994: mov      x0, x20 ;
00185f998: bl       #0x17884c8 ; ServerTimeModule$$get_ServerTime
00185f99c: ldr      x20, [x19, #0x40] ;
00185f9a0: mov      x19, x0 ;
00185f9a4: cbnz     x20, #0x185f9ac ;
00185f9a8: bl       #0x3f564f0 ;
00185f9ac: ldr      w20, [x20, #0xbc] ;
00185f9b0: cbnz     x19, #0x185f9b8 ;
00185f9b4: bl       #0x3f564f0 ;
00185f9b8: mov      x1, xzr ;
00185f9bc: mov      x0, x19 ;
00185f9c0: bl       #0x3e5112c ; ServerTime$$GetServerTime
00185f9c4: ldp      x29, x30, [sp, #0x10] ;
00185f9c8: sub      w8, w20, w0 ;
00185f9cc: cmp      w8, #0 ;
00185f9d0: cset     w0, gt ;
00185f9d4: ldp      x20, x19, [sp], #0x20 ;
00185f9d8: ret       ;
