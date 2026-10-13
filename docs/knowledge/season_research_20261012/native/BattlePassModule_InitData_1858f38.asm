; BattlePassModule$$InitData
; RVA [0x1858f38,0x18597a0), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 c80460a332786b5b4f87bb24c039b52d3b99decc59c438abd9886bd41eff5652
001858f38: stp      x24, x23, [sp, #-0x40]! ;
001858f3c: stp      x22, x21, [sp, #0x10] ;
001858f40: stp      x20, x19, [sp, #0x20] ;
001858f44: stp      x29, x30, [sp, #0x30] ;
001858f48: add      x29, sp, #0x30 ;
001858f4c: adrp     x20, #0x5577000 ;
001858f50: ldrb     w8, [x20, #0x66c] ;
001858f54: mov      x19, x0 ;
001858f58: tbnz     w8, #0, #0x1858f74 ;
001858f5c: adrp     x8, #0x51dc000 ;
001858f60: ldr      x8, [x8, #0x648] ;
001858f64: ldr      w0, [x8] ;
001858f68: bl       #0x3f2aed0 ;
001858f6c: mov      w8, #1 ;
001858f70: strb     w8, [x20, #0x66c] ;
001858f74: mov      x1, xzr ;
001858f78: mov      x0, x19 ;
001858f7c: bl       #0x144108c ; Foundation.Module.BusinessModule$$InitData
001858f80: ldr      x20, [x19, #0x48] ;
001858f84: str      wzr, [x19, #0x1c] ;
001858f88: str      wzr, [x19, #0x14] ;
001858f8c: cbnz     x20, #0x1858f94 ;
001858f90: bl       #0x3f564f0 ;
001858f94: adrp     x8, #0x5272000 ;
001858f98: ldr      x8, [x8, #0x4a0] ;
001858f9c: mov      x0, x20 ;
001858fa0: ldr      x1, [x8] ;
001858fa4: bl       #0x32bd008 ; System.Collections.Generic.Dictionary<int, BattlePassType>$$Clear
001858fa8: adrp     x8, #0x521b000 ;
001858fac: ldr      x8, [x8, #0x890] ;
001858fb0: ldr      x0, [x8] ;
001858fb4: adrp     x8, #0x51d2000 ;
001858fb8: ldr      x8, [x8, #0x9a8] ;
001858fbc: ldr      x20, [x8] ;
001858fc0: ldrb     w8, [x0, #0x10a] ;
001858fc4: tbz      w8, #0, #0x1858fd4 ;
001858fc8: ldr      w8, [x0, #0xbc] ;
001858fcc: cbnz     w8, #0x1858fd4 ;
001858fd0: bl       #0x3f3f378 ;
001858fd4: mov      x0, xzr ;
001858fd8: mov      x2, xzr ;
001858fdc: mov      x1, x20 ;
001858fe0: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001858fe4: adrp     x8, #0x51f8000 ;
001858fe8: adrp     x23, #0x51de000 ;
001858fec: ldr      x8, [x8, #0x278] ;
001858ff0: ldr      x23, [x23, #0xc78] ;
001858ff4: mov      x20, x0 ;
001858ff8: ldr      x22, [x8] ;
001858ffc: ldr      x8, [x23] ;
001859000: mov      x0, x8 ;
001859004: bl       #0x3f6452c ;
001859008: adrp     x24, #0x5264000 ;
00185900c: ldr      x24, [x24, #0xd40] ;
001859010: mov      x1, x19 ;
001859014: mov      x2, x22 ;
001859018: mov      x21, x0 ;
00185901c: ldr      x3, [x24] ;
001859020: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
001859024: adrp     x8, #0x5227000 ;
001859028: ldr      x8, [x8, #0x168] ;
00185902c: ldr      x0, [x8] ;
001859030: ldrb     w8, [x0, #0x10a] ;
001859034: tbz      w8, #0, #0x1859044 ;
001859038: ldr      w8, [x0, #0xbc] ;
00185903c: cbnz     w8, #0x1859044 ;
001859040: bl       #0x3f3f378 ;
001859044: mov      x0, xzr ;
001859048: mov      x3, xzr ;
00185904c: mov      x1, x20 ;
001859050: mov      x2, x21 ;
001859054: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
001859058: adrp     x8, #0x52f7000 ;
00185905c: ldr      x8, [x8, #0x620] ;
001859060: mov      x0, xzr ;
001859064: mov      x2, xzr ;
001859068: ldr      x1, [x8] ;
00185906c: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001859070: adrp     x8, #0x5236000 ;
001859074: ldr      x8, [x8, #0x770] ;
001859078: mov      x21, x0 ;
00185907c: ldr      x20, [x8] ;
001859080: ldr      x8, [x23] ;
001859084: mov      x0, x8 ;
001859088: bl       #0x3f6452c ;
00185908c: ldr      x3, [x24] ;
001859090: mov      x1, x19 ;
001859094: mov      x2, x20 ;
001859098: mov      x22, x0 ;
00185909c: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
0018590a0: mov      x0, xzr ;
0018590a4: mov      x3, xzr ;
0018590a8: mov      x1, x21 ;
0018590ac: mov      x2, x22 ;
0018590b0: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
0018590b4: adrp     x8, #0x51e4000 ;
0018590b8: ldr      x8, [x8, #0x250] ;
0018590bc: mov      x0, xzr ;
0018590c0: mov      x2, xzr ;
0018590c4: ldr      x1, [x8] ;
0018590c8: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
0018590cc: adrp     x8, #0x52b2000 ;
0018590d0: ldr      x8, [x8, #0xa28] ;
0018590d4: mov      x21, x0 ;
0018590d8: ldr      x20, [x8] ;
0018590dc: ldr      x8, [x23] ;
0018590e0: mov      x0, x8 ;
0018590e4: bl       #0x3f6452c ;
0018590e8: ldr      x3, [x24] ;
0018590ec: mov      x1, x19 ;
0018590f0: mov      x2, x20 ;
0018590f4: mov      x22, x0 ;
0018590f8: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
0018590fc: mov      x0, xzr ;
001859100: mov      x3, xzr ;
001859104: mov      x1, x21 ;
001859108: mov      x2, x22 ;
00185910c: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
001859110: adrp     x8, #0x5236000 ;
001859114: ldr      x8, [x8, #0xea0] ;
001859118: mov      x0, xzr ;
00185911c: mov      x2, xzr ;
001859120: ldr      x1, [x8] ;
001859124: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001859128: adrp     x8, #0x529f000 ;
00185912c: ldr      x8, [x8, #0xb50] ;
001859130: mov      x21, x0 ;
001859134: ldr      x20, [x8] ;
001859138: ldr      x8, [x23] ;
00185913c: mov      x0, x8 ;
001859140: bl       #0x3f6452c ;
001859144: ldr      x3, [x24] ;
001859148: mov      x1, x19 ;
00185914c: mov      x2, x20 ;
001859150: mov      x22, x0 ;
001859154: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
001859158: mov      x0, xzr ;
00185915c: mov      x3, xzr ;
001859160: mov      x1, x21 ;
001859164: mov      x2, x22 ;
001859168: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
00185916c: adrp     x8, #0x52b1000 ;
001859170: ldr      x8, [x8, #0x658] ;
001859174: mov      x0, xzr ;
001859178: mov      x2, xzr ;
00185917c: ldr      x1, [x8] ;
001859180: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001859184: adrp     x8, #0x51df000 ;
001859188: ldr      x8, [x8, #0xd48] ;
00185918c: mov      x21, x0 ;
001859190: ldr      x20, [x8] ;
001859194: ldr      x8, [x23] ;
001859198: mov      x0, x8 ;
00185919c: bl       #0x3f6452c ;
0018591a0: ldr      x3, [x24] ;
0018591a4: mov      x1, x19 ;
0018591a8: mov      x2, x20 ;
0018591ac: mov      x22, x0 ;
0018591b0: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
0018591b4: mov      x0, xzr ;
0018591b8: mov      x3, xzr ;
0018591bc: mov      x1, x21 ;
0018591c0: mov      x2, x22 ;
0018591c4: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
0018591c8: adrp     x8, #0x52f1000 ;
0018591cc: ldr      x8, [x8, #0xd58] ;
0018591d0: mov      x0, xzr ;
0018591d4: mov      x2, xzr ;
0018591d8: ldr      x1, [x8] ;
0018591dc: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
0018591e0: adrp     x8, #0x51c9000 ;
0018591e4: ldr      x8, [x8, #0x6d8] ;
0018591e8: mov      x21, x0 ;
0018591ec: ldr      x20, [x8] ;
0018591f0: ldr      x8, [x23] ;
0018591f4: mov      x0, x8 ;
0018591f8: bl       #0x3f6452c ;
0018591fc: ldr      x3, [x24] ;
001859200: mov      x1, x19 ;
001859204: mov      x2, x20 ;
001859208: mov      x22, x0 ;
00185920c: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
001859210: mov      x0, xzr ;
001859214: mov      x3, xzr ;
001859218: mov      x1, x21 ;
00185921c: mov      x2, x22 ;
001859220: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
001859224: adrp     x8, #0x51d4000 ;
001859228: ldr      x8, [x8, #0xbe0] ;
00185922c: mov      x0, xzr ;
001859230: mov      x2, xzr ;
001859234: ldr      x1, [x8] ;
001859238: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
00185923c: adrp     x8, #0x5226000 ;
001859240: ldr      x8, [x8, #0x2f0] ;
001859244: mov      x21, x0 ;
001859248: ldr      x20, [x8] ;
00185924c: ldr      x8, [x23] ;
001859250: mov      x0, x8 ;
001859254: bl       #0x3f6452c ;
001859258: ldr      x3, [x24] ;
00185925c: mov      x1, x19 ;
001859260: mov      x2, x20 ;
001859264: mov      x22, x0 ;
001859268: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
00185926c: mov      x0, xzr ;
001859270: mov      x3, xzr ;
001859274: mov      x1, x21 ;
001859278: mov      x2, x22 ;
00185927c: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
001859280: adrp     x8, #0x5292000 ;
001859284: ldr      x8, [x8, #0xfc0] ;
001859288: mov      x0, xzr ;
00185928c: mov      x2, xzr ;
001859290: ldr      x1, [x8] ;
001859294: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001859298: adrp     x8, #0x528b000 ;
00185929c: ldr      x8, [x8, #0xa18] ;
0018592a0: mov      x21, x0 ;
0018592a4: ldr      x20, [x8] ;
0018592a8: ldr      x8, [x23] ;
0018592ac: mov      x0, x8 ;
0018592b0: bl       #0x3f6452c ;
0018592b4: ldr      x3, [x24] ;
0018592b8: mov      x1, x19 ;
0018592bc: mov      x2, x20 ;
0018592c0: mov      x22, x0 ;
0018592c4: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
0018592c8: mov      x0, xzr ;
0018592cc: mov      x3, xzr ;
0018592d0: mov      x1, x21 ;
0018592d4: mov      x2, x22 ;
0018592d8: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
0018592dc: adrp     x8, #0x51f0000 ;
0018592e0: ldr      x8, [x8, #0xcc0] ;
0018592e4: mov      x0, xzr ;
0018592e8: mov      x2, xzr ;
0018592ec: ldr      x1, [x8] ;
0018592f0: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
0018592f4: adrp     x8, #0x51fc000 ;
0018592f8: ldr      x8, [x8, #0xed8] ;
0018592fc: mov      x21, x0 ;
001859300: ldr      x20, [x8] ;
001859304: ldr      x8, [x23] ;
001859308: mov      x0, x8 ;
00185930c: bl       #0x3f6452c ;
001859310: ldr      x3, [x24] ;
001859314: mov      x1, x19 ;
001859318: mov      x2, x20 ;
00185931c: mov      x22, x0 ;
001859320: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
001859324: mov      x0, xzr ;
001859328: mov      x3, xzr ;
00185932c: mov      x1, x21 ;
001859330: mov      x2, x22 ;
001859334: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
001859338: adrp     x8, #0x5281000 ;
00185933c: ldr      x8, [x8, #0x4f8] ;
001859340: mov      x0, xzr ;
001859344: mov      x2, xzr ;
001859348: ldr      x1, [x8] ;
00185934c: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001859350: adrp     x8, #0x5273000 ;
001859354: ldr      x8, [x8, #0xfd0] ;
001859358: mov      x21, x0 ;
00185935c: ldr      x20, [x8] ;
001859360: ldr      x8, [x23] ;
001859364: mov      x0, x8 ;
001859368: bl       #0x3f6452c ;
00185936c: ldr      x3, [x24] ;
001859370: mov      x1, x19 ;
001859374: mov      x2, x20 ;
001859378: mov      x22, x0 ;
00185937c: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
001859380: mov      x0, xzr ;
001859384: mov      x3, xzr ;
001859388: mov      x1, x21 ;
00185938c: mov      x2, x22 ;
001859390: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
001859394: adrp     x8, #0x523b000 ;
001859398: ldr      x8, [x8, #0xf18] ;
00185939c: mov      x0, xzr ;
0018593a0: mov      x2, xzr ;
0018593a4: ldr      x1, [x8] ;
0018593a8: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
0018593ac: adrp     x8, #0x5218000 ;
0018593b0: ldr      x8, [x8, #0xd20] ;
0018593b4: mov      x21, x0 ;
0018593b8: ldr      x20, [x8] ;
0018593bc: ldr      x8, [x23] ;
0018593c0: mov      x0, x8 ;
0018593c4: bl       #0x3f6452c ;
0018593c8: ldr      x3, [x24] ;
0018593cc: mov      x1, x19 ;
0018593d0: mov      x2, x20 ;
0018593d4: mov      x22, x0 ;
0018593d8: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
0018593dc: mov      x0, xzr ;
0018593e0: mov      x3, xzr ;
0018593e4: mov      x1, x21 ;
0018593e8: mov      x2, x22 ;
0018593ec: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
0018593f0: adrp     x8, #0x52db000 ;
0018593f4: ldr      x8, [x8, #0x3e8] ;
0018593f8: mov      x0, xzr ;
0018593fc: mov      x2, xzr ;
001859400: ldr      x1, [x8] ;
001859404: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001859408: adrp     x8, #0x51fb000 ;
00185940c: ldr      x8, [x8, #0x30] ;
001859410: mov      x21, x0 ;
001859414: ldr      x20, [x8] ;
001859418: ldr      x8, [x23] ;
00185941c: mov      x0, x8 ;
001859420: bl       #0x3f6452c ;
001859424: ldr      x3, [x24] ;
001859428: mov      x1, x19 ;
00185942c: mov      x2, x20 ;
001859430: mov      x22, x0 ;
001859434: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
001859438: mov      x0, xzr ;
00185943c: mov      x3, xzr ;
001859440: mov      x1, x21 ;
001859444: mov      x2, x22 ;
001859448: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
00185944c: adrp     x8, #0x5236000 ;
001859450: ldr      x8, [x8, #0x648] ;
001859454: mov      x0, xzr ;
001859458: mov      x2, xzr ;
00185945c: ldr      x1, [x8] ;
001859460: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001859464: adrp     x8, #0x51fc000 ;
001859468: ldr      x8, [x8, #0xac0] ;
00185946c: mov      x21, x0 ;
001859470: ldr      x20, [x8] ;
001859474: ldr      x8, [x23] ;
001859478: mov      x0, x8 ;
00185947c: bl       #0x3f6452c ;
001859480: ldr      x3, [x24] ;
001859484: mov      x1, x19 ;
001859488: mov      x2, x20 ;
00185948c: mov      x22, x0 ;
001859490: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
001859494: mov      x0, xzr ;
001859498: mov      x3, xzr ;
00185949c: mov      x1, x21 ;
0018594a0: mov      x2, x22 ;
0018594a4: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
0018594a8: adrp     x8, #0x52c9000 ;
0018594ac: adrp     x9, #0x51d9000 ;
0018594b0: ldr      x8, [x8, #0x910] ;
0018594b4: ldr      x9, [x9, #0xec8] ;
0018594b8: ldr      x21, [x8] ;
0018594bc: ldr      x0, [x9] ;
0018594c0: bl       #0x3f6452c ;
0018594c4: adrp     x8, #0x5215000 ;
0018594c8: ldr      x8, [x8, #0x2e8] ;
0018594cc: mov      x1, x19 ;
0018594d0: mov      x2, x21 ;
0018594d4: mov      x20, x0 ;
0018594d8: ldr      x3, [x8] ;
0018594dc: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
0018594e0: adrp     x8, #0x5210000 ;
0018594e4: ldr      x8, [x8, #0xf98] ;
0018594e8: ldr      x0, [x8] ;
0018594ec: ldrb     w8, [x0, #0x10a] ;
0018594f0: tbz      w8, #0, #0x1859500 ;
0018594f4: ldr      w8, [x0, #0xbc] ;
0018594f8: cbnz     w8, #0x1859500 ;
0018594fc: bl       #0x3f3f378 ;
001859500: adrp     x8, #0x528c000 ;
001859504: ldr      x8, [x8, #0x220] ;
001859508: mov      x0, xzr ;
00185950c: mov      w1, #0x116 ;
001859510: mov      x2, x20 ;
001859514: ldr      x3, [x8] ;
001859518: bl       #0x221f598 ; CommonX2.X2EventManager$$RegisterEvent<W2C_WorldBossPlayerAct>
00185951c: adrp     x8, #0x5279000 ;
001859520: ldr      x8, [x8, #0x58] ;
001859524: mov      x0, xzr ;
001859528: mov      x2, xzr ;
00185952c: ldr      x1, [x8] ;
001859530: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001859534: adrp     x8, #0x51f2000 ;
001859538: ldr      x8, [x8, #0xc20] ;
00185953c: mov      x21, x0 ;
001859540: ldr      x20, [x8] ;
001859544: ldr      x8, [x23] ;
001859548: mov      x0, x8 ;
00185954c: bl       #0x3f6452c ;
001859550: ldr      x3, [x24] ;
001859554: mov      x1, x19 ;
001859558: mov      x2, x20 ;
00185955c: mov      x22, x0 ;
001859560: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
001859564: mov      x0, xzr ;
001859568: mov      x3, xzr ;
00185956c: mov      x1, x21 ;
001859570: mov      x2, x22 ;
001859574: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
001859578: adrp     x8, #0x5260000 ;
00185957c: ldr      x8, [x8, #0xaa0] ;
001859580: mov      x0, xzr ;
001859584: mov      x2, xzr ;
001859588: ldr      x1, [x8] ;
00185958c: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001859590: adrp     x8, #0x5204000 ;
001859594: ldr      x8, [x8, #0xd80] ;
001859598: mov      x21, x0 ;
00185959c: ldr      x20, [x8] ;
0018595a0: ldr      x8, [x23] ;
0018595a4: mov      x0, x8 ;
0018595a8: bl       #0x3f6452c ;
0018595ac: ldr      x3, [x24] ;
0018595b0: mov      x1, x19 ;
0018595b4: mov      x2, x20 ;
0018595b8: mov      x22, x0 ;
0018595bc: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
0018595c0: mov      x0, xzr ;
0018595c4: mov      x3, xzr ;
0018595c8: mov      x1, x21 ;
0018595cc: mov      x2, x22 ;
0018595d0: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
0018595d4: adrp     x8, #0x51fd000 ;
0018595d8: ldr      x8, [x8, #0x40] ;
0018595dc: mov      x0, xzr ;
0018595e0: mov      x2, xzr ;
0018595e4: ldr      x1, [x8] ;
0018595e8: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
0018595ec: adrp     x8, #0x52e2000 ;
0018595f0: ldr      x8, [x8, #0x290] ;
0018595f4: mov      x21, x0 ;
0018595f8: ldr      x20, [x8] ;
0018595fc: ldr      x8, [x23] ;
001859600: mov      x0, x8 ;
001859604: bl       #0x3f6452c ;
001859608: ldr      x3, [x24] ;
00185960c: mov      x1, x19 ;
001859610: mov      x2, x20 ;
001859614: mov      x22, x0 ;
001859618: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
00185961c: mov      x0, xzr ;
001859620: mov      x3, xzr ;
001859624: mov      x1, x21 ;
001859628: mov      x2, x22 ;
00185962c: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
001859630: adrp     x8, #0x52e2000 ;
001859634: ldr      x8, [x8, #0xfd8] ;
001859638: mov      x0, xzr ;
00185963c: mov      x2, xzr ;
001859640: ldr      x1, [x8] ;
001859644: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001859648: adrp     x8, #0x51df000 ;
00185964c: ldr      x8, [x8, #0xb40] ;
001859650: mov      x21, x0 ;
001859654: ldr      x20, [x8] ;
001859658: ldr      x8, [x23] ;
00185965c: mov      x0, x8 ;
001859660: bl       #0x3f6452c ;
001859664: ldr      x3, [x24] ;
001859668: mov      x1, x19 ;
00185966c: mov      x2, x20 ;
001859670: mov      x22, x0 ;
001859674: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
001859678: mov      x0, xzr ;
00185967c: mov      x3, xzr ;
001859680: mov      x1, x21 ;
001859684: mov      x2, x22 ;
001859688: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
00185968c: adrp     x8, #0x521f000 ;
001859690: ldr      x8, [x8, #0x410] ;
001859694: mov      x0, xzr ;
001859698: mov      x2, xzr ;
00185969c: ldr      x1, [x8] ;
0018596a0: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
0018596a4: adrp     x8, #0x5206000 ;
0018596a8: ldr      x8, [x8, #0xc28] ;
0018596ac: mov      x21, x0 ;
0018596b0: ldr      x20, [x8] ;
0018596b4: ldr      x8, [x23] ;
0018596b8: mov      x0, x8 ;
0018596bc: bl       #0x3f6452c ;
0018596c0: ldr      x3, [x24] ;
0018596c4: mov      x1, x19 ;
0018596c8: mov      x2, x20 ;
0018596cc: mov      x22, x0 ;
0018596d0: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
0018596d4: mov      x0, xzr ;
0018596d8: mov      x3, xzr ;
0018596dc: mov      x1, x21 ;
0018596e0: mov      x2, x22 ;
0018596e4: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
0018596e8: adrp     x8, #0x5259000 ;
0018596ec: adrp     x9, #0x5276000 ;
0018596f0: ldr      x8, [x8, #0x668] ;
0018596f4: ldr      x9, [x9, #0x858] ;
0018596f8: ldr      x20, [x8] ;
0018596fc: ldr      x0, [x9] ;
001859700: bl       #0x3f6452c ;
001859704: adrp     x8, #0x5295000 ;
001859708: ldr      x8, [x8, #0xc08] ;
00185970c: mov      x1, x19 ;
001859710: mov      x2, x20 ;
001859714: mov      x21, x0 ;
001859718: ldr      x3, [x8] ;
00185971c: bl       #0x262a528 ; System.Action<int, int>$$.ctor
001859720: adrp     x8, #0x52ee000 ;
001859724: ldr      x8, [x8, #0x7c8] ;
001859728: mov      x0, xzr ;
00185972c: mov      w1, #0x174 ;
001859730: mov      x2, x21 ;
001859734: ldr      x3, [x8] ;
001859738: bl       #0x221e0c8 ; CommonX2.X2EventManager$$RegisterEvent<int, int>
00185973c: adrp     x8, #0x524c000 ;
001859740: ldr      x8, [x8, #0xde8] ;
001859744: ldr      x0, [x8] ;
001859748: ldrb     w8, [x0, #0x10a] ;
00185974c: tbz      w8, #0, #0x185975c ;
001859750: ldr      w8, [x0, #0xbc] ;
001859754: cbnz     w8, #0x185975c ;
001859758: bl       #0x3f3f378 ;
00185975c: mov      x0, xzr ;
001859760: mov      x1, xzr ;
001859764: bl       #0x17e5448 ; BadgeViewMgr$$get_Instance
001859768: mov      x20, x0 ;
00185976c: str      x20, [x19, #0x68] ;
001859770: cbnz     x20, #0x1859778 ;
001859774: bl       #0x3f564f0 ;
001859778: mov      w1, wzr ;
00185977c: mov      x2, xzr ;
001859780: mov      x0, x20 ;
001859784: bl       #0x18008fc ; BadgeViewMgr$$CreateBadge
001859788: str      w0, [x19, #0x70] ;
00185978c: ldp      x29, x30, [sp, #0x30] ;
001859790: ldp      x20, x19, [sp, #0x20] ;
001859794: ldp      x22, x21, [sp, #0x10] ;
001859798: ldp      x24, x23, [sp], #0x40 ;
00185979c: ret       ;
