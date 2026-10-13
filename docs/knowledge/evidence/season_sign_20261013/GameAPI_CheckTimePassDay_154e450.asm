; GameAPI$$CheckTimePassDay
; RVA [0x154e450,0x154e620), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 3489afa49fe815ce2ad9186e66f96f2d2809ada5bcc60ae84c11062fbcc5a946
00154e450: stp      x22, x21, [sp, #-0x30]! ;
00154e454: stp      x20, x19, [sp, #0x10] ;
00154e458: stp      x29, x30, [sp, #0x20] ;
00154e45c: add      x29, sp, #0x20 ;
00154e460: adrp     x20, #0x5576000 ;
00154e464: ldrb     w8, [x20, #0x1bb] ;
00154e468: mov      x19, x1 ;
00154e46c: tbnz     w8, #0, #0x154e488 ;
00154e470: adrp     x8, #0x5286000 ;
00154e474: ldr      x8, [x8, #0x9c8] ;
00154e478: ldr      w0, [x8] ;
00154e47c: bl       #0x3f2aed0 ;
00154e480: mov      w8, #1 ;
00154e484: strb     w8, [x20, #0x1bb] ;
00154e488: adrp     x8, #0x51ed000 ;
00154e48c: ldr      x8, [x8, #0xb60] ;
00154e490: ldr      x0, [x8] ;
00154e494: ldrb     w8, [x0, #0x10a] ;
00154e498: tbz      w8, #0, #0x154e4a8 ;
00154e49c: ldr      w8, [x0, #0xbc] ;
00154e4a0: cbnz     w8, #0x154e4a8 ;
00154e4a4: bl       #0x3f3f378 ;
00154e4a8: adrp     x8, #0x51d9000 ;
00154e4ac: ldr      x8, [x8, #0x618] ;
00154e4b0: mov      x0, xzr ;
00154e4b4: ldr      x1, [x8] ;
00154e4b8: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
00154e4bc: mov      x20, x0 ;
00154e4c0: cbnz     x20, #0x154e4c8 ;
00154e4c4: bl       #0x3f564f0 ;
00154e4c8: adrp     x8, #0x5262000 ;
00154e4cc: ldr      x8, [x8, #0xdb8] ;
00154e4d0: mov      x0, x20 ;
00154e4d4: ldr      x1, [x8] ;
00154e4d8: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
00154e4dc: mov      x20, x0 ;
00154e4e0: cbnz     x20, #0x154e4e8 ;
00154e4e4: bl       #0x3f564f0 ;
00154e4e8: mov      x1, xzr ;
00154e4ec: mov      x0, x20 ;
00154e4f0: bl       #0x17884c8 ; ServerTimeModule$$get_ServerTime
00154e4f4: mov      x22, x0 ;
00154e4f8: mov      x0, xzr ;
00154e4fc: mov      w2, wzr ;
00154e500: mov      x1, x19 ;
00154e504: mov      w3, wzr ;
00154e508: mov      w4, wzr ;
00154e50c: mov      x5, xzr ;
00154e510: bl       #0x3e48df8 ; DateTimeHelper$$GetTempDateTimeFrom2018
00154e514: mov      x21, x0 ;
00154e518: cbz      x22, #0x154e530 ;
00154e51c: mov      x1, xzr ;
00154e520: mov      x0, x22 ;
00154e524: bl       #0x3e51248 ; ServerTime$$GetTempServerDateTimeDate
00154e528: mov      x20, x0 ;
00154e52c: b        #0x154e548 ;
00154e530: bl       #0x3f564f0 ;
00154e534: mov      x0, xzr ;
00154e538: mov      x1, xzr ;
00154e53c: bl       #0x3e51248 ; ServerTime$$GetTempServerDateTimeDate
00154e540: mov      x20, x0 ;
00154e544: bl       #0x3f564f0 ;
00154e548: mov      x2, xzr ;
00154e54c: mov      x0, x22 ;
00154e550: mov      x1, x19 ;
00154e554: bl       #0x3e51abc ; ServerTime$$GetTempPassTime
00154e558: mov      x19, x0 ;
00154e55c: cbnz     x19, #0x154e564 ;
00154e560: bl       #0x3f564f0 ;
00154e564: mov      x1, xzr ;
00154e568: mov      x0, x19 ;
00154e56c: bl       #0x3e496e4 ; DateTimeHelper.TimeSpanDate$$get_Days
00154e570: cmp      w0, #1 ;
00154e574: b.gt     #0x154e5ec ;
00154e578: cbnz     x21, #0x154e580 ;
00154e57c: bl       #0x3f564f0 ;
00154e580: mov      x1, xzr ;
00154e584: mov      x0, x21 ;
00154e588: bl       #0x3e4919c ; DateTimeHelper.DateTimeDate$$get_Day
00154e58c: mov      w19, w0 ;
00154e590: cbnz     x20, #0x154e598 ;
00154e594: bl       #0x3f564f0 ;
00154e598: mov      x1, xzr ;
00154e59c: mov      x0, x20 ;
00154e5a0: bl       #0x3e4919c ; DateTimeHelper.DateTimeDate$$get_Day
00154e5a4: cmp      w19, w0 ;
00154e5a8: b.ne     #0x154e5f4 ;
00154e5ac: cbnz     x21, #0x154e5b4 ;
00154e5b0: bl       #0x3f564f0 ;
00154e5b4: mov      x1, xzr ;
00154e5b8: mov      x0, x21 ;
00154e5bc: bl       #0x3e48ba8 ; DateTimeHelper.DateTimeDate$$get_Hour
00154e5c0: cmp      w0, #4 ;
00154e5c4: b.gt     #0x154e5e4 ;
00154e5c8: cbnz     x20, #0x154e5d0 ;
00154e5cc: bl       #0x3f564f0 ;
00154e5d0: mov      x1, xzr ;
00154e5d4: mov      x0, x20 ;
00154e5d8: bl       #0x3e48ba8 ; DateTimeHelper.DateTimeDate$$get_Hour
00154e5dc: cmp      w0, #4 ;
00154e5e0: b.gt     #0x154e5ec ;
00154e5e4: mov      w0, wzr ;
00154e5e8: b        #0x154e610 ;
00154e5ec: mov      w0, #1 ;
00154e5f0: b        #0x154e610 ;
00154e5f4: cbnz     x20, #0x154e5fc ;
00154e5f8: bl       #0x3f564f0 ;
00154e5fc: mov      x1, xzr ;
00154e600: mov      x0, x20 ;
00154e604: bl       #0x3e48ba8 ; DateTimeHelper.DateTimeDate$$get_Hour
00154e608: cmp      w0, #4 ;
00154e60c: cset     w0, gt ;
00154e610: ldp      x29, x30, [sp, #0x20] ;
00154e614: ldp      x20, x19, [sp, #0x10] ;
00154e618: ldp      x22, x21, [sp], #0x30 ;
00154e61c: ret       ;
