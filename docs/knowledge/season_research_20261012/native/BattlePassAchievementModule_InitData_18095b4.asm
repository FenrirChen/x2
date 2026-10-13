; BattlePassAchievementModule$$InitData
; RVA [0x18095b4,0x18099fc), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 97ab8e17a75f595c11868b447e7fd1646b1eeaafe994bd7b8e6f43f3525bc1fa
0018095b4: stp      x24, x23, [sp, #-0x40]! ;
0018095b8: stp      x22, x21, [sp, #0x10] ;
0018095bc: stp      x20, x19, [sp, #0x20] ;
0018095c0: stp      x29, x30, [sp, #0x30] ;
0018095c4: add      x29, sp, #0x30 ;
0018095c8: adrp     x20, #0x5577000 ;
0018095cc: ldrb     w8, [x20, #0x436] ;
0018095d0: mov      x19, x0 ;
0018095d4: tbnz     w8, #0, #0x18095f0 ;
0018095d8: adrp     x8, #0x51e1000 ;
0018095dc: ldr      x8, [x8, #0x4e0] ;
0018095e0: ldr      w0, [x8] ;
0018095e4: bl       #0x3f2aed0 ;
0018095e8: mov      w8, #1 ;
0018095ec: strb     w8, [x20, #0x436] ;
0018095f0: mov      x1, xzr ;
0018095f4: mov      x0, x19 ;
0018095f8: bl       #0x144108c ; Foundation.Module.BusinessModule$$InitData
0018095fc: adrp     x8, #0x521b000 ;
001809600: ldr      x8, [x8, #0x890] ;
001809604: ldr      x0, [x8] ;
001809608: adrp     x8, #0x5290000 ;
00180960c: ldr      x8, [x8, #0xee0] ;
001809610: ldr      x20, [x8] ;
001809614: ldrb     w8, [x0, #0x10a] ;
001809618: tbz      w8, #0, #0x1809628 ;
00180961c: ldr      w8, [x0, #0xbc] ;
001809620: cbnz     w8, #0x1809628 ;
001809624: bl       #0x3f3f378 ;
001809628: mov      x0, xzr ;
00180962c: mov      x2, xzr ;
001809630: mov      x1, x20 ;
001809634: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001809638: adrp     x8, #0x520d000 ;
00180963c: adrp     x23, #0x51de000 ;
001809640: ldr      x8, [x8, #0xd40] ;
001809644: ldr      x23, [x23, #0xc78] ;
001809648: mov      x20, x0 ;
00180964c: ldr      x22, [x8] ;
001809650: ldr      x8, [x23] ;
001809654: mov      x0, x8 ;
001809658: bl       #0x3f6452c ;
00180965c: adrp     x24, #0x5264000 ;
001809660: ldr      x24, [x24, #0xd40] ;
001809664: mov      x1, x19 ;
001809668: mov      x2, x22 ;
00180966c: mov      x21, x0 ;
001809670: ldr      x3, [x24] ;
001809674: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
001809678: adrp     x8, #0x5227000 ;
00180967c: ldr      x8, [x8, #0x168] ;
001809680: ldr      x0, [x8] ;
001809684: ldrb     w8, [x0, #0x10a] ;
001809688: tbz      w8, #0, #0x1809698 ;
00180968c: ldr      w8, [x0, #0xbc] ;
001809690: cbnz     w8, #0x1809698 ;
001809694: bl       #0x3f3f378 ;
001809698: mov      x0, xzr ;
00180969c: mov      x3, xzr ;
0018096a0: mov      x1, x20 ;
0018096a4: mov      x2, x21 ;
0018096a8: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
0018096ac: adrp     x8, #0x5278000 ;
0018096b0: ldr      x8, [x8, #0xbc8] ;
0018096b4: mov      x0, xzr ;
0018096b8: mov      x2, xzr ;
0018096bc: ldr      x1, [x8] ;
0018096c0: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
0018096c4: adrp     x8, #0x5269000 ;
0018096c8: ldr      x8, [x8, #0x798] ;
0018096cc: mov      x21, x0 ;
0018096d0: ldr      x20, [x8] ;
0018096d4: ldr      x8, [x23] ;
0018096d8: mov      x0, x8 ;
0018096dc: bl       #0x3f6452c ;
0018096e0: ldr      x3, [x24] ;
0018096e4: mov      x1, x19 ;
0018096e8: mov      x2, x20 ;
0018096ec: mov      x22, x0 ;
0018096f0: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
0018096f4: mov      x0, xzr ;
0018096f8: mov      x3, xzr ;
0018096fc: mov      x1, x21 ;
001809700: mov      x2, x22 ;
001809704: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
001809708: adrp     x8, #0x5235000 ;
00180970c: ldr      x8, [x8, #0xc88] ;
001809710: mov      x0, xzr ;
001809714: mov      x2, xzr ;
001809718: ldr      x1, [x8] ;
00180971c: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
001809720: adrp     x8, #0x5220000 ;
001809724: ldr      x8, [x8, #0x5e0] ;
001809728: mov      x21, x0 ;
00180972c: ldr      x20, [x8] ;
001809730: ldr      x8, [x23] ;
001809734: mov      x0, x8 ;
001809738: bl       #0x3f6452c ;
00180973c: ldr      x3, [x24] ;
001809740: mov      x1, x19 ;
001809744: mov      x2, x20 ;
001809748: mov      x22, x0 ;
00180974c: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
001809750: mov      x0, xzr ;
001809754: mov      x3, xzr ;
001809758: mov      x1, x21 ;
00180975c: mov      x2, x22 ;
001809760: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
001809764: adrp     x8, #0x521f000 ;
001809768: ldr      x8, [x8, #0xa80] ;
00180976c: mov      x0, xzr ;
001809770: mov      x2, xzr ;
001809774: ldr      x1, [x8] ;
001809778: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
00180977c: adrp     x8, #0x5206000 ;
001809780: ldr      x8, [x8, #0xca0] ;
001809784: mov      x21, x0 ;
001809788: ldr      x20, [x8] ;
00180978c: ldr      x8, [x23] ;
001809790: mov      x0, x8 ;
001809794: bl       #0x3f6452c ;
001809798: ldr      x3, [x24] ;
00180979c: mov      x1, x19 ;
0018097a0: mov      x2, x20 ;
0018097a4: mov      x22, x0 ;
0018097a8: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
0018097ac: mov      x0, xzr ;
0018097b0: mov      x3, xzr ;
0018097b4: mov      x1, x21 ;
0018097b8: mov      x2, x22 ;
0018097bc: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
0018097c0: adrp     x8, #0x5301000 ;
0018097c4: ldr      x8, [x8, #0x448] ;
0018097c8: mov      x0, xzr ;
0018097cc: mov      x2, xzr ;
0018097d0: ldr      x1, [x8] ;
0018097d4: bl       #0x2d6d7c0 ; System.Type$$GetTypeFromHandle
0018097d8: adrp     x8, #0x527c000 ;
0018097dc: ldr      x8, [x8, #0x430] ;
0018097e0: mov      x21, x0 ;
0018097e4: ldr      x20, [x8] ;
0018097e8: ldr      x8, [x23] ;
0018097ec: mov      x0, x8 ;
0018097f0: bl       #0x3f6452c ;
0018097f4: ldr      x3, [x24] ;
0018097f8: mov      x1, x19 ;
0018097fc: mov      x2, x20 ;
001809800: mov      x22, x0 ;
001809804: bl       #0x262250c ; System.Action<Response<SetValueReply>>$$.ctor
001809808: mov      x0, xzr ;
00180980c: mov      x3, xzr ;
001809810: mov      x1, x21 ;
001809814: mov      x2, x22 ;
001809818: bl       #0x141ff5c ; MarsNetManager$$AddMessageHandler
00180981c: adrp     x8, #0x51ed000 ;
001809820: ldr      x8, [x8, #0xb60] ;
001809824: ldr      x0, [x8] ;
001809828: ldrb     w8, [x0, #0x10a] ;
00180982c: tbz      w8, #0, #0x180983c ;
001809830: ldr      w8, [x0, #0xbc] ;
001809834: cbnz     w8, #0x180983c ;
001809838: bl       #0x3f3f378 ;
00180983c: adrp     x8, #0x51d9000 ;
001809840: ldr      x8, [x8, #0x618] ;
001809844: mov      x0, xzr ;
001809848: ldr      x1, [x8] ;
00180984c: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
001809850: mov      x20, x0 ;
001809854: cbnz     x20, #0x180985c ;
001809858: bl       #0x3f564f0 ;
00180985c: adrp     x8, #0x5246000 ;
001809860: ldr      x8, [x8, #0xfd8] ;
001809864: mov      x0, x20 ;
001809868: ldr      x1, [x8] ;
00180986c: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
001809870: ldr      x21, [x19, #0x70] ;
001809874: mov      x20, x0 ;
001809878: cbnz     x21, #0x1809880 ;
00180987c: bl       #0x3f564f0 ;
001809880: mov      w1, wzr ;
001809884: mov      x2, xzr ;
001809888: mov      x0, x21 ;
00180988c: bl       #0x18008fc ; BadgeViewMgr$$CreateBadge
001809890: ldr      x21, [x19, #0x70] ;
001809894: str      w0, [x19, #0x20] ;
001809898: cbnz     x21, #0x18098a0 ;
00180989c: bl       #0x3f564f0 ;
0018098a0: mov      w1, wzr ;
0018098a4: mov      x2, xzr ;
0018098a8: mov      x0, x21 ;
0018098ac: bl       #0x18008fc ; BadgeViewMgr$$CreateBadge
0018098b0: ldr      x21, [x19, #0x70] ;
0018098b4: str      w0, [x19, #0x24] ;
0018098b8: cbnz     x21, #0x18098c0 ;
0018098bc: bl       #0x3f564f0 ;
0018098c0: mov      w1, wzr ;
0018098c4: mov      x2, xzr ;
0018098c8: mov      x0, x21 ;
0018098cc: bl       #0x18008fc ; BadgeViewMgr$$CreateBadge
0018098d0: ldr      x21, [x19, #0x70] ;
0018098d4: str      w0, [x19, #0x28] ;
0018098d8: cbnz     x21, #0x18098e0 ;
0018098dc: bl       #0x3f564f0 ;
0018098e0: mov      w1, wzr ;
0018098e4: mov      x2, xzr ;
0018098e8: mov      x0, x21 ;
0018098ec: bl       #0x18008fc ; BadgeViewMgr$$CreateBadge
0018098f0: ldr      x21, [x19, #0x70] ;
0018098f4: str      w0, [x19, #0x2c] ;
0018098f8: cbnz     x21, #0x1809900 ;
0018098fc: bl       #0x3f564f0 ;
001809900: mov      w1, wzr ;
001809904: mov      x2, xzr ;
001809908: mov      x0, x21 ;
00180990c: bl       #0x18008fc ; BadgeViewMgr$$CreateBadge
001809910: ldr      x21, [x19, #0x70] ;
001809914: str      w0, [x19, #0x30] ;
001809918: cbnz     x20, #0x1809920 ;
00180991c: bl       #0x3f564f0 ;
001809920: mov      x1, xzr ;
001809924: mov      x0, x20 ;
001809928: bl       #0x1858364 ; BattlePassModule$$get_MainBadge
00180992c: ldr      w20, [x19, #0x20] ;
001809930: mov      w22, w0 ;
001809934: cbnz     x21, #0x180993c ;
001809938: bl       #0x3f564f0 ;
00180993c: mov      x3, xzr ;
001809940: mov      x0, x21 ;
001809944: mov      w1, w22 ;
001809948: mov      w2, w20 ;
00180994c: bl       #0x1800e34 ; BadgeViewMgr$$AddChild
001809950: ldr      x20, [x19, #0x70] ;
001809954: ldp      w21, w22, [x19, #0x20] ;
001809958: cbnz     x20, #0x1809960 ;
00180995c: bl       #0x3f564f0 ;
001809960: mov      x3, xzr ;
001809964: mov      x0, x20 ;
001809968: mov      w1, w21 ;
00180996c: mov      w2, w22 ;
001809970: bl       #0x1800e34 ; BadgeViewMgr$$AddChild
001809974: ldr      x20, [x19, #0x70] ;
001809978: ldr      w21, [x19, #0x20] ;
00180997c: ldr      w22, [x19, #0x28] ;
001809980: cbnz     x20, #0x1809988 ;
001809984: bl       #0x3f564f0 ;
001809988: mov      x3, xzr ;
00180998c: mov      x0, x20 ;
001809990: mov      w1, w21 ;
001809994: mov      w2, w22 ;
001809998: bl       #0x1800e34 ; BadgeViewMgr$$AddChild
00180999c: ldr      x20, [x19, #0x70] ;
0018099a0: ldr      w21, [x19, #0x20] ;
0018099a4: ldr      w22, [x19, #0x2c] ;
0018099a8: cbnz     x20, #0x18099b0 ;
0018099ac: bl       #0x3f564f0 ;
0018099b0: mov      x3, xzr ;
0018099b4: mov      x0, x20 ;
0018099b8: mov      w1, w21 ;
0018099bc: mov      w2, w22 ;
0018099c0: bl       #0x1800e34 ; BadgeViewMgr$$AddChild
0018099c4: ldr      x20, [x19, #0x70] ;
0018099c8: ldr      w21, [x19, #0x20] ;
0018099cc: ldr      w19, [x19, #0x30] ;
0018099d0: cbnz     x20, #0x18099d8 ;
0018099d4: bl       #0x3f564f0 ;
0018099d8: mov      x0, x20 ;
0018099dc: mov      w1, w21 ;
0018099e0: mov      w2, w19 ;
0018099e4: ldp      x29, x30, [sp, #0x30] ;
0018099e8: ldp      x20, x19, [sp, #0x20] ;
0018099ec: ldp      x22, x21, [sp, #0x10] ;
0018099f0: mov      x3, xzr ;
0018099f4: ldp      x24, x23, [sp], #0x40 ;
0018099f8: b        #0x1800e34 ; BadgeViewMgr$$AddChild
