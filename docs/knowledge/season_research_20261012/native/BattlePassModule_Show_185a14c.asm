; BattlePassModule$$Show
; RVA [0x185a14c,0x185a2cc), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 c30e5fd35a4dfb655bfa266702d1ffd8d9394c72626a5d2857df2335759a1ecf
00185a14c: stp      x22, x21, [sp, #-0x30]! ;
00185a150: stp      x20, x19, [sp, #0x10] ;
00185a154: stp      x29, x30, [sp, #0x20] ;
00185a158: add      x29, sp, #0x20 ;
00185a15c: adrp     x20, #0x5577000 ;
00185a160: ldrb     w8, [x20, #0x66e] ;
00185a164: mov      x19, x0 ;
00185a168: tbnz     w8, #0, #0x185a184 ;
00185a16c: adrp     x8, #0x5300000 ;
00185a170: ldr      x8, [x8, #0x4e8] ;
00185a174: ldr      w0, [x8] ;
00185a178: bl       #0x3f2aed0 ;
00185a17c: mov      w8, #1 ;
00185a180: strb     w8, [x20, #0x66e] ;
00185a184: mov      x1, xzr ;
00185a188: mov      x0, x19 ;
00185a18c: bl       #0x1453404 ; Foundation.Module.BusinessModule$$Show
00185a190: adrp     x8, #0x528b000 ;
00185a194: ldr      x8, [x8, #0x2e0] ;
00185a198: ldr      x0, [x8] ;
00185a19c: ldrb     w8, [x0, #0x10a] ;
00185a1a0: tbz      w8, #0, #0x185a1b0 ;
00185a1a4: ldr      w8, [x0, #0xbc] ;
00185a1a8: cbnz     w8, #0x185a1b0 ;
00185a1ac: bl       #0x3f3f378 ;
00185a1b0: mov      x0, xzr ;
00185a1b4: mov      w1, #0x23 ;
00185a1b8: mov      w2, #1 ;
00185a1bc: mov      x3, xzr ;
00185a1c0: bl       #0x1522c14 ; GameAPI$$IsServerFunctionClose
00185a1c4: and      w8, w0, #1 ;
00185a1c8: tbnz     w8, #0, #0x185a2bc ;
00185a1cc: adrp     x8, #0x51ed000 ;
00185a1d0: ldr      x8, [x8, #0xb60] ;
00185a1d4: ldr      x0, [x8] ;
00185a1d8: ldrb     w8, [x0, #0x10a] ;
00185a1dc: tbz      w8, #0, #0x185a1ec ;
00185a1e0: ldr      w8, [x0, #0xbc] ;
00185a1e4: cbnz     w8, #0x185a1ec ;
00185a1e8: bl       #0x3f3f378 ;
00185a1ec: adrp     x8, #0x51d9000 ;
00185a1f0: ldr      x8, [x8, #0x618] ;
00185a1f4: mov      x0, xzr ;
00185a1f8: ldr      x1, [x8] ;
00185a1fc: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
00185a200: mov      x20, x0 ;
00185a204: cbnz     x20, #0x185a20c ;
00185a208: bl       #0x3f564f0 ;
00185a20c: adrp     x8, #0x5252000 ;
00185a210: ldr      x8, [x8, #0xae0] ;
00185a214: mov      x0, x20 ;
00185a218: ldr      x1, [x8] ;
00185a21c: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
00185a220: mov      x20, x0 ;
00185a224: cbnz     x20, #0x185a22c ;
00185a228: bl       #0x3f564f0 ;
00185a22c: mov      x3, xzr ;
00185a230: mov      w1, #0x38 ;
00185a234: mov      w2, #1 ;
00185a238: mov      x0, x20 ;
00185a23c: bl       #0x1317cf4 ; ActivityNoticeModule$$CheckActivityOpen
00185a240: tbz      w0, #0, #0x185a2bc ;
00185a244: bl       #0x1858d9c ; BattlePassModule$$GetBattlePassMainPrefab
00185a248: adrp     x8, #0x52dd000 ;
00185a24c: ldr      x8, [x8, #0x4f8] ;
00185a250: mov      x20, x0 ;
00185a254: ldr      x8, [x8] ;
00185a258: ldrb     w9, [x8, #0x10a] ;
00185a25c: tbz      w9, #0, #0x185a270 ;
00185a260: ldr      w9, [x8, #0xbc] ;
00185a264: cbnz     w9, #0x185a270 ;
00185a268: mov      x0, x8 ;
00185a26c: bl       #0x3f3f378 ;
00185a270: mov      x0, xzr ;
00185a274: mov      x1, xzr ;
00185a278: bl       #0x1441694 ; Foundation.UI.UIManager$$get_Instance
00185a27c: mov      x21, x0 ;
00185a280: cbnz     x21, #0x185a288 ;
00185a284: bl       #0x3f564f0 ;
00185a288: adrp     x8, #0x52e5000 ;
00185a28c: ldr      x8, [x8, #0xda8] ;
00185a290: mov      x2, xzr ;
00185a294: mov      w3, #1 ;
00185a298: mov      x0, x21 ;
00185a29c: ldr      x4, [x8] ;
00185a2a0: mov      x1, x20 ;
00185a2a4: bl       #0x3e90710 ; Foundation.UI.UIManager$$OpenUI<PlotSkipWindow>
00185a2a8: mov      x0, x19 ;
00185a2ac: ldp      x29, x30, [sp, #0x20] ;
00185a2b0: ldp      x20, x19, [sp, #0x10] ;
00185a2b4: ldp      x22, x21, [sp], #0x30 ;
00185a2b8: b        #0x185a2cc ; BattlePassModule$$PlayBGM
00185a2bc: ldp      x29, x30, [sp, #0x20] ;
00185a2c0: ldp      x20, x19, [sp, #0x10] ;
00185a2c4: ldp      x22, x21, [sp], #0x30 ;
00185a2c8: ret       ;
