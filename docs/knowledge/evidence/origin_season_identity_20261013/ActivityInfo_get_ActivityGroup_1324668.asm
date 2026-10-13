; ActivityInfo$$get_ActivityGroup
; RVA [0x1324668,0x13246c4), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 11b658b0af8e956e6ea574d01e3eda127a94d3673fa7e009002cfdde07ac3da4
001324668: stp      x20, x19, [sp, #-0x20]! ;
00132466c: stp      x29, x30, [sp, #0x10] ;
001324670: add      x29, sp, #0x10 ;
001324674: mov      x19, x0 ;
001324678: ldr      x20, [x19, #0x10] ;
00132467c: cbnz     x20, #0x1324684 ;
001324680: bl       #0x3f564f0 ;
001324684: ldr      w8, [x20, #0x18] ;
001324688: cmp      w8, #2 ;
00132468c: b.ne     #0x13246a4 ;
001324690: ldr      x19, [x19, #0x10] ;
001324694: cbnz     x19, #0x132469c ;
001324698: bl       #0x3f564f0 ;
00132469c: add      x8, x19, #0x30 ;
0013246a0: b        #0x13246b4 ;
0013246a4: ldr      x19, [x19, #0x18] ;
0013246a8: cbnz     x19, #0x13246b0 ;
0013246ac: bl       #0x3f564f0 ;
0013246b0: add      x8, x19, #0x1c ;
0013246b4: ldr      w0, [x8] ;
0013246b8: ldp      x29, x30, [sp, #0x10] ;
0013246bc: ldp      x20, x19, [sp], #0x20 ;
0013246c0: ret       ;
