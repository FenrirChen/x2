; WorldBossModule$$UpdateChallengeWorldBossInfoChange
; RVA [0x1374020,0x13742c8), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 b8724a870d87b36cc3e13f6fa0e3261465f1d9c075d9fb44ed73f9a0c1158290
001374020: stp      x22, x21, [sp, #-0x30]! ;
001374024: stp      x20, x19, [sp, #0x10] ;
001374028: stp      x29, x30, [sp, #0x20] ;
00137402c: add      x29, sp, #0x20 ;
001374030: adrp     x21, #0x5575000 ;
001374034: ldrb     w8, [x21, #0x550] ;
001374038: mov      x19, x1 ;
00137403c: mov      x20, x0 ;
001374040: tbnz     w8, #0, #0x137405c ;
001374044: adrp     x8, #0x51cd000 ;
001374048: ldr      x8, [x8, #0x820] ;
00137404c: ldr      w0, [x8] ;
001374050: bl       #0x3f2aed0 ;
001374054: mov      w8, #1 ;
001374058: strb     w8, [x21, #0x550] ;
00137405c: ldr      x8, [x20, #0x60] ;
001374060: cbz      x8, #0x1374260 ;
001374064: cbz      x19, #0x1374260 ;
001374068: adrp     x9, #0x5285000 ;
00137406c: ldr      x9, [x9, #0x500] ;
001374070: ldr      x22, [x8, #0x10] ;
001374074: ldr      x21, [x19, #0x10] ;
001374078: ldr      x0, [x9] ;
00137407c: ldrb     w8, [x0, #0x10a] ;
001374080: tbz      w8, #0, #0x1374090 ;
001374084: ldr      w8, [x0, #0xbc] ;
001374088: cbnz     w8, #0x1374090 ;
00137408c: bl       #0x3f3f378 ;
001374090: mov      x0, xzr ;
001374094: mov      x3, xzr ;
001374098: mov      x1, x22 ;
00137409c: mov      x2, x21 ;
0013740a0: bl       #0x2b80c20 ; System.String$$op_Equality
0013740a4: tbz      w0, #0, #0x1374260 ;
0013740a8: mov      x0, x20 ;
0013740ac: mov      x1, x19 ;
0013740b0: bl       #0x136f2fc ; WorldBossModule$$set_CurChallengeBossInfo
0013740b4: ldr      x21, [x20, #0x38] ;
0013740b8: ldr      x22, [x19, #0x10] ;
0013740bc: cbnz     x21, #0x13740c4 ;
0013740c0: bl       #0x3f564f0 ;
0013740c4: adrp     x8, #0x52f2000 ;
0013740c8: ldr      x8, [x8, #0xdd8] ;
0013740cc: mov      x0, x21 ;
0013740d0: mov      x1, x22 ;
0013740d4: mov      x2, x19 ;
0013740d8: ldr      x3, [x8] ;
0013740dc: bl       #0x35b62a8 ; System.Collections.Generic.Dictionary<Type, Func<Delegate, Delegate>>$$set_Item
0013740e0: adrp     x8, #0x5210000 ;
0013740e4: ldr      x8, [x8, #0xf98] ;
0013740e8: ldr      x0, [x8] ;
0013740ec: ldrb     w8, [x0, #0x10a] ;
0013740f0: tbz      w8, #0, #0x1374100 ;
0013740f4: ldr      w8, [x0, #0xbc] ;
0013740f8: cbnz     w8, #0x1374100 ;
0013740fc: bl       #0x3f3f378 ;
001374100: mov      x0, xzr ;
001374104: mov      w1, #0x3e ;
001374108: mov      x2, xzr ;
00137410c: bl       #0x3e48998 ; CommonX2.X2EventManager$$FireEvent
001374110: ldr      w8, [x19, #0x30] ;
001374114: sub      w8, w8, #1 ;
001374118: cmp      w8, #3 ;
00137411c: b.hi     #0x1374260 ;
001374120: adrp     x9, #0x4187000 ;
001374124: add      x9, x9, #0x768 ;
001374128: ldrsw    x8, [x9, x8, lsl #2] ;
00137412c: add      x8, x8, x9 ;
001374130: br       x8 ;
001374134: mov      x0, x20 ;
001374138: ldp      x29, x30, [sp, #0x20] ;
00137413c: ldp      x20, x19, [sp, #0x10] ;
001374140: ldp      x22, x21, [sp], #0x30 ;
001374144: b        #0x1375ed0 ; WorldBossModule$$RefreshMassTimer
001374148: adrp     x21, #0x52e3000 ;
00137414c: ldr      x21, [x21, #0x530] ;
001374150: ldr      x0, [x21] ;
001374154: ldrb     w8, [x0, #0x10a] ;
001374158: tbz      w8, #0, #0x1374168 ;
00137415c: ldr      w8, [x0, #0xbc] ;
001374160: cbnz     w8, #0x1374168 ;
001374164: bl       #0x3f3f378 ;
001374168: mov      x0, xzr ;
00137416c: mov      x1, xzr ;
001374170: bl       #0x1379e68 ; GameAppImpl$$GetInstance
001374174: cbz      x0, #0x1374260 ;
001374178: ldr      x0, [x21] ;
00137417c: ldrb     w8, [x0, #0x10a] ;
001374180: tbz      w8, #0, #0x1374190 ;
001374184: ldr      w8, [x0, #0xbc] ;
001374188: cbnz     w8, #0x1374190 ;
00137418c: bl       #0x3f3f378 ;
001374190: mov      x0, xzr ;
001374194: mov      x1, xzr ;
001374198: bl       #0x1379e68 ; GameAppImpl$$GetInstance
00137419c: mov      x21, x0 ;
0013741a0: cbnz     x21, #0x13741a8 ;
0013741a4: bl       #0x3f564f0 ;
0013741a8: ldr      w8, [x21, #0x28] ;
0013741ac: cmp      w8, #2 ;
0013741b0: b.ne     #0x13741c4 ;
0013741b4: ldr      w8, [x20, #0x84] ;
0013741b8: cbnz     w8, #0x13741c4 ;
0013741bc: mov      x0, x20 ;
0013741c0: bl       #0x1376090 ; WorldBossModule$$StartEnterTimer
0013741c4: mov      x0, xzr ;
0013741c8: mov      x1, xzr ;
0013741cc: bl       #0x18d3144 ; LogicX2.LogicBattle$$get_Current
0013741d0: cbz      x0, #0x1374260 ;
0013741d4: mov      x0, xzr ;
0013741d8: mov      x1, xzr ;
0013741dc: bl       #0x18d3144 ; LogicX2.LogicBattle$$get_Current
0013741e0: mov      x20, x0 ;
0013741e4: cbnz     x20, #0x13741ec ;
0013741e8: bl       #0x3f564f0 ;
0013741ec: mov      x1, xzr ;
0013741f0: mov      x0, x20 ;
0013741f4: bl       #0x18e80b4 ; LogicX2.LogicBattle$$get_BattleInfo
0013741f8: cbz      x0, #0x1374260 ;
0013741fc: mov      x0, xzr ;
001374200: mov      x1, xzr ;
001374204: bl       #0x18d3144 ; LogicX2.LogicBattle$$get_Current
001374208: adrp     x8, #0x5300000 ;
00137420c: ldr      x8, [x8, #0xcc0] ;
001374210: mov      x20, x0 ;
001374214: ldr      x8, [x8] ;
001374218: mov      x0, x8 ;
00137421c: bl       #0x3f6452c ;
001374220: mov      x1, xzr ;
001374224: mov      x21, x0 ;
001374228: bl       #0x1c5b6d4 ; LogicX2Command.WorldBossHPSync$$.ctor
00137422c: ldr      x19, [x19, #0x60] ;
001374230: cbnz     x21, #0x1374238 ;
001374234: bl       #0x3f564f0 ;
001374238: str      x19, [x21, #0x18] ;
00137423c: cbnz     x20, #0x1374244 ;
001374240: bl       #0x3f564f0 ;
001374244: mov      x0, x20 ;
001374248: ldp      x29, x30, [sp, #0x20] ;
00137424c: ldp      x20, x19, [sp, #0x10] ;
001374250: mov      x2, xzr ;
001374254: mov      x1, x21 ;
001374258: ldp      x22, x21, [sp], #0x30 ;
00137425c: b        #0x18f6b30 ; LogicX2.LogicBattle$$OnInput
001374260: ldp      x29, x30, [sp, #0x20] ;
001374264: ldp      x20, x19, [sp, #0x10] ;
001374268: ldp      x22, x21, [sp], #0x30 ;
00137426c: ret       ;
001374270: ldr      w1, [x20, #0x84] ;
001374274: cbz      w1, #0x1374288 ;
001374278: mov      x0, xzr ;
00137427c: mov      x2, xzr ;
001374280: bl       #0x3e534c0 ; X2Timer.TimerManager$$Delete
001374284: str      wzr, [x20, #0x84] ;
001374288: mov      x0, x20 ;
00137428c: ldp      x29, x30, [sp, #0x20] ;
001374290: ldp      x20, x19, [sp, #0x10] ;
001374294: ldp      x22, x21, [sp], #0x30 ;
001374298: b        #0x13759e4 ; WorldBossModule$$DoBossOverPerformance
00137429c: ldr      w1, [x20, #0x84] ;
0013742a0: cbz      w1, #0x13742b4 ;
0013742a4: mov      x0, xzr ;
0013742a8: mov      x2, xzr ;
0013742ac: bl       #0x3e534c0 ; X2Timer.TimerManager$$Delete
0013742b0: str      wzr, [x20, #0x84] ;
0013742b4: mov      x0, x20 ;
0013742b8: ldp      x29, x30, [sp, #0x20] ;
0013742bc: ldp      x20, x19, [sp, #0x10] ;
0013742c0: ldp      x22, x21, [sp], #0x30 ;
0013742c4: b        #0x13762c8 ; WorldBossModule$$DoBossDisMissPerformance
