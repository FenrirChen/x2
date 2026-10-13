; BattlePassModule$$GetBattlePassChapterPrefab
; RVA [0x1858928,0x1858a0c), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 94d1d1d9d6d2193de2ee6d21564f2989be38bb37ee49b4e13abd22eada088255
001858928: stp      x20, x19, [sp, #-0x20]! ;
00185892c: stp      x29, x30, [sp, #0x10] ;
001858930: add      x29, sp, #0x10 ;
001858934: adrp     x19, #0x5577000 ;
001858938: ldrb     w8, [x19, #0x665] ;
00185893c: tbnz     w8, #0, #0x1858958 ;
001858940: adrp     x8, #0x524e000 ;
001858944: ldr      x8, [x8, #0x4e8] ;
001858948: ldr      w0, [x8] ;
00185894c: bl       #0x3f2aed0 ;
001858950: mov      w8, #1 ;
001858954: strb     w8, [x19, #0x665] ;
001858958: adrp     x8, #0x51ed000 ;
00185895c: ldr      x8, [x8, #0xb60] ;
001858960: ldr      x0, [x8] ;
001858964: ldrb     w8, [x0, #0x10a] ;
001858968: tbz      w8, #0, #0x1858978 ;
00185896c: ldr      w8, [x0, #0xbc] ;
001858970: cbnz     w8, #0x1858978 ;
001858974: bl       #0x3f3f378 ;
001858978: adrp     x8, #0x51d9000 ;
00185897c: ldr      x8, [x8, #0x618] ;
001858980: mov      x0, xzr ;
001858984: ldr      x1, [x8] ;
001858988: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
00185898c: mov      x19, x0 ;
001858990: cbnz     x19, #0x1858998 ;
001858994: bl       #0x3f564f0 ;
001858998: adrp     x8, #0x5252000 ;
00185899c: ldr      x8, [x8, #0xae0] ;
0018589a0: mov      x0, x19 ;
0018589a4: ldr      x1, [x8] ;
0018589a8: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
0018589ac: cbz      x0, #0x18589f4 ;
0018589b0: mov      x2, xzr ;
0018589b4: mov      w1, #0x38 ;
0018589b8: bl       #0x132e22c ; ActivityNoticeModule$$GetActivityData
0018589bc: adrp     x19, #0x523a000 ;
0018589c0: ldr      x19, [x19, #0x20] ;  STRING_REF='UI_MapChoose'
0018589c4: cbz      x0, #0x18589fc ;
0018589c8: mov      x1, xzr ;
0018589cc: bl       #0x1324668 ; ActivityInfo$$get_ActivityGroup
0018589d0: adrp     x8, #0x51db000 ;
0018589d4: ldr      x8, [x8, #0xf40] ;  STRING_REF='UI_MapChoose2'
0018589d8: adrp     x9, #0x5202000 ;
0018589dc: ldr      x9, [x9, #0x518] ;  STRING_REF='UI_MapChoose3'
0018589e0: cmp      w0, #0x17 ;
0018589e4: csel     x8, x8, x19, eq ;
0018589e8: cmp      w0, #0x22 ;
0018589ec: csel     x19, x9, x8, eq ;
0018589f0: b        #0x18589fc ;
0018589f4: adrp     x19, #0x523a000 ;
0018589f8: ldr      x19, [x19, #0x20] ;  STRING_REF='UI_MapChoose'
0018589fc: ldr      x0, [x19] ;
001858a00: ldp      x29, x30, [sp, #0x10] ;
001858a04: ldp      x20, x19, [sp], #0x20 ;
001858a08: ret       ;
