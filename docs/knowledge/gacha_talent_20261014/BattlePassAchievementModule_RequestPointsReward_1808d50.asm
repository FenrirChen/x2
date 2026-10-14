; BattlePassAchievementModule$$RequestPointsReward
; RVA [0x1808d50,0x1808f28), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 b9edb2529a324c75089768a652667deab55e766adb70c662be3ef1f85d6ec081
001808d50: stp      x22, x21, [sp, #-0x30]! ;
001808d54: stp      x20, x19, [sp, #0x10] ;
001808d58: stp      x29, x30, [sp, #0x20] ;
001808d5c: add      x29, sp, #0x20 ;
001808d60: adrp     x20, #0x5577000 ;
001808d64: ldrb     w8, [x20, #0x43b] ;
001808d68: mov      w19, w1 ;
001808d6c: tbnz     w8, #0, #0x1808d88 ;
001808d70: adrp     x8, #0x526a000 ;
001808d74: ldr      x8, [x8, #0xa58] ;
001808d78: ldr      w0, [x8] ;
001808d7c: bl       #0x3f2aed0 ;
001808d80: mov      w8, #1 ;
001808d84: strb     w8, [x20, #0x43b] ;
001808d88: adrp     x8, #0x51ed000 ;
001808d8c: ldr      x8, [x8, #0xb60] ;
001808d90: ldr      x0, [x8] ;
001808d94: ldrb     w8, [x0, #0x10a] ;
001808d98: tbz      w8, #0, #0x1808da8 ;
001808d9c: ldr      w8, [x0, #0xbc] ;
001808da0: cbnz     w8, #0x1808da8 ;
001808da4: bl       #0x3f3f378 ;
001808da8: adrp     x8, #0x51d9000 ;
001808dac: ldr      x8, [x8, #0x618] ;
001808db0: mov      x0, xzr ;
001808db4: ldr      x1, [x8] ;
001808db8: bl       #0x2feb968 ; Foundation.Module.ServiceModule<ModuleManager>$$get_Instance
001808dbc: mov      x20, x0 ;
001808dc0: cbnz     x20, #0x1808dc8 ;
001808dc4: bl       #0x3f564f0 ;
001808dc8: adrp     x8, #0x52d1000 ;
001808dcc: ldr      x8, [x8, #0x868] ;
001808dd0: mov      x0, x20 ;
001808dd4: ldr      x1, [x8] ;
001808dd8: bl       #0x1ce72d4 ; Foundation.Module.ModuleManager$$GetModule<RelicBarModule>
001808ddc: mov      x20, x0 ;
001808de0: cbnz     x20, #0x1808de8 ;
001808de4: bl       #0x3f564f0 ;
001808de8: strb     wzr, [x20, #0x2c] ;
001808dec: adrp     x8, #0x52f0000 ;
001808df0: ldr      x8, [x8, #0x80] ;
001808df4: ldr      x0, [x8] ;
001808df8: ldrb     w8, [x0, #0x10a] ;
001808dfc: tbz      w8, #0, #0x1808e0c ;
001808e00: ldr      w8, [x0, #0xbc] ;
001808e04: cbnz     w8, #0x1808e0c ;
001808e08: bl       #0x3f3f378 ;
001808e0c: mov      x0, xzr ;
001808e10: mov      x1, xzr ;
001808e14: bl       #0x1598a88 ; TaskControlManager$$get_Instance
001808e18: mov      x20, x0 ;
001808e1c: cbnz     x20, #0x1808e24 ;
001808e20: bl       #0x3f564f0 ;
001808e24: mov      x2, xzr ;
001808e28: mov      w1, #5 ;
001808e2c: mov      x0, x20 ;
001808e30: bl       #0x1598d58 ; TaskControlManager$$GetItem
001808e34: mov      x20, x0 ;
001808e38: cbz      x20, #0x1808e90 ;
001808e3c: ldr      x21, [x20, #0x88] ;
001808e40: cbnz     x21, #0x1808e48 ;
001808e44: bl       #0x3f564f0 ;
001808e48: adrp     x8, #0x5300000 ;
001808e4c: ldr      x8, [x8, #0xfa8] ;
001808e50: mov      x0, x21 ;
001808e54: ldr      x1, [x8] ;
001808e58: bl       #0x3d473f8 ; System.Collections.Generic.List<int>$$get_Count
001808e5c: cmp      w0, w19 ;
001808e60: b.le     #0x1808e90 ;
001808e64: ldr      x20, [x20, #0x88] ;
001808e68: cbnz     x20, #0x1808e70 ;
001808e6c: bl       #0x3f564f0 ;
001808e70: adrp     x8, #0x52e6000 ;
001808e74: ldr      x8, [x8, #0x7b0] ;
001808e78: mov      x0, x20 ;
001808e7c: mov      w1, w19 ;
001808e80: ldr      x2, [x8] ;
001808e84: bl       #0x3d47400 ; System.Collections.Generic.List<int>$$get_Item
001808e88: mov      w19, w0 ;
001808e8c: b        #0x1808e94 ;
001808e90: mov      w19, wzr ;
001808e94: adrp     x8, #0x5227000 ;
001808e98: ldr      x8, [x8, #0x168] ;
001808e9c: ldr      x0, [x8] ;
001808ea0: ldrb     w8, [x0, #0x10a] ;
001808ea4: tbz      w8, #0, #0x1808eb4 ;
001808ea8: ldr      w8, [x0, #0xbc] ;
001808eac: cbnz     w8, #0x1808eb4 ;
001808eb0: bl       #0x3f3f378 ;
001808eb4: mov      x0, xzr ;
001808eb8: mov      x1, xzr ;
001808ebc: bl       #0x141a6c8 ; MarsNetManager$$get_Instance
001808ec0: adrp     x8, #0x5228000 ;
001808ec4: ldr      x8, [x8, #0x470] ;
001808ec8: mov      x20, x0 ;
001808ecc: ldr      x8, [x8] ;
001808ed0: mov      x0, x8 ;
001808ed4: bl       #0x3f6452c ;
001808ed8: mov      x1, xzr ;
001808edc: mov      x21, x0 ;
001808ee0: bl       #0x3a1b228 ; CommandX2.C2L_SeasonAchvPointReward$$.ctor
001808ee4: cbnz     x21, #0x1808eec ;
001808ee8: bl       #0x3f564f0 ;
001808eec: str      w19, [x21, #0x10] ;
001808ef0: cbnz     x20, #0x1808ef8 ;
001808ef4: bl       #0x3f564f0 ;
001808ef8: adrp     x8, #0x52a2000 ;
001808efc: ldr      x8, [x8, #0xeb8] ;
001808f00: mov      x0, x20 ;
001808f04: mov      w2, wzr ;
001808f08: mov      w4, wzr ;
001808f0c: ldr      x5, [x8] ;
001808f10: ldp      x29, x30, [sp, #0x20] ;
001808f14: ldp      x20, x19, [sp, #0x10] ;
001808f18: mov      w3, #1 ;
001808f1c: mov      x1, x21 ;
001808f20: ldp      x22, x21, [sp], #0x30 ;
001808f24: b        #0x233d7ac ; MarsNetManager$$Send<C2L_ReissueDialogReciveInfo>
