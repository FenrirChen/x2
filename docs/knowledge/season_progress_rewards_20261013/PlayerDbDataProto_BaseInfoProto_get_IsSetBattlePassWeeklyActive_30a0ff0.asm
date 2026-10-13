; PlayerDbDataProto.BaseInfoProto$$get_IsSetBattlePassWeeklyActive
; RVA [0x30a0ff0,0x30a1020), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 2b6f1df31f2ccf51bbf1b47022e3e43dbaf941496f7b069974e11afbd8451b2d
0030a0ff0: stp      x20, x19, [sp, #-0x20]! ;
0030a0ff4: stp      x29, x30, [sp, #0x10] ;
0030a0ff8: add      x29, sp, #0x10 ;
0030a0ffc: ldr      x19, [x0, #0x10] ;
0030a1000: cbnz     x19, #0x30a1008 ;
0030a1004: bl       #0x3f564f0 ;
0030a1008: ldp      x29, x30, [sp, #0x10] ;
0030a100c: mov      x2, xzr ;
0030a1010: mov      w1, #0x43 ;
0030a1014: mov      x0, x19 ;
0030a1018: ldp      x20, x19, [sp], #0x20 ;
0030a101c: b        #0x2df9664 ; System.Collections.BitArray$$Get
