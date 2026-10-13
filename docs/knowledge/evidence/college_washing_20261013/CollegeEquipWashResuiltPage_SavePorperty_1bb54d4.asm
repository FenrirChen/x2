; CollegeEquipWashResuiltPage$$SavePorperty
; RVA [0x1bb54d4,0x1bb558c), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 707085908e98916f3b9c8b52f0f162c15167dbfeefe022ffdc6eb3b3fa1fb6e7
001bb54d4: stp      x20, x19, [sp, #-0x20]! ;
001bb54d8: stp      x29, x30, [sp, #0x10] ;
001bb54dc: add      x29, sp, #0x10 ;
001bb54e0: adrp     x20, #0x5578000 ;
001bb54e4: ldrb     w8, [x20, #0xc91] ;
001bb54e8: mov      x19, x0 ;
001bb54ec: tbnz     w8, #0, #0x1bb5508 ;
001bb54f0: adrp     x8, #0x5290000 ;
001bb54f4: ldr      x8, [x8, #0x750] ;
001bb54f8: ldr      w0, [x8] ;
001bb54fc: bl       #0x3f2aed0 ;
001bb5500: mov      w8, #1 ;
001bb5504: strb     w8, [x20, #0xc91] ;
001bb5508: adrp     x8, #0x51ed000 ;
001bb550c: ldr      x8, [x8, #0xb60] ;
001bb5510: ldr      x0, [x8] ;
001bb5514: ldrb     w8, [x0, #0x10a] ;
001bb5518: tbz      w8, #0, #0x1bb5528 ;
001bb551c: ldr      w8, [x0, #0xbc] ;
001bb5520: cbnz     w8, #0x1bb5528 ;
001bb5524: bl       #0x3f3f378 ;
001bb5528: adrp     x8, #0x51d9000 ;
001bb552c: ldr      x8, [x8, #0x618] ;
001bb5530: mov      x0, xzr ;
001bb5534: ldr      x1, [x8] ;
001bb5538: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
001bb553c: mov      x20, x0 ;
001bb5540: cbnz     x20, #0x1bb5548 ;
001bb5544: bl       #0x3f564f0 ;
001bb5548: adrp     x8, #0x52ca000 ;
001bb554c: ldr      x8, [x8, #0xf70] ;
001bb5550: mov      x0, x20 ;
001bb5554: ldr      x1, [x8] ;
001bb5558: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
001bb555c: ldr      w19, [x19, #0xb8] ;
001bb5560: mov      x20, x0 ;
001bb5564: cbnz     x20, #0x1bb556c ;
001bb5568: bl       #0x3f564f0 ;
001bb556c: ldp      x29, x30, [sp, #0x10] ;
001bb5570: mov      x3, xzr ;
001bb5574: mov      x4, xzr ;
001bb5578: mov      w2, #5 ;
001bb557c: mov      x0, x20 ;
001bb5580: mov      w1, w19 ;
001bb5584: ldp      x20, x19, [sp], #0x20 ;
001bb5588: b        #0x1b006fc ; CollegeModule$$SendWashingRoomOpt
