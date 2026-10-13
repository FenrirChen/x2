; BattlePassModule$$GetSelectBattlePassChallengeId
; RVA [0x1861aec,0x1861d10), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 c6811f3124bc1961d5f277dd9001afc0c769d78d5ce1bb3040c9bb6c3cc1e045
001861aec: stp      x28, x27, [sp, #-0x60]! ;
001861af0: stp      x26, x25, [sp, #0x10] ;
001861af4: stp      x24, x23, [sp, #0x20] ;
001861af8: stp      x22, x21, [sp, #0x30] ;
001861afc: stp      x20, x19, [sp, #0x40] ;
001861b00: stp      x29, x30, [sp, #0x50] ;
001861b04: add      x29, sp, #0x50 ;
001861b08: adrp     x20, #0x5577000 ;
001861b0c: ldrb     w8, [x20, #0x6a9] ;
001861b10: mov      x19, x0 ;
001861b14: tbnz     w8, #0, #0x1861b30 ;
001861b18: adrp     x8, #0x5310000 ;
001861b1c: ldr      x8, [x8, #0x388] ;
001861b20: ldr      w0, [x8] ;
001861b24: bl       #0x3f2aed0 ;
001861b28: mov      w8, #1 ;
001861b2c: strb     w8, [x20, #0x6a9] ;
001861b30: ldr      w1, [x19, #0x13c] ;
001861b34: cmp      w1, #0 ;
001861b38: b.gt     #0x1861b98 ;
001861b3c: adrp     x8, #0x52ba000 ;
001861b40: ldr      x8, [x8, #0x898] ;
001861b44: ldr      x0, [x8] ;
001861b48: ldrb     w8, [x0, #0x10a] ;
001861b4c: tbz      w8, #0, #0x1861b5c ;
001861b50: ldr      w8, [x0, #0xbc] ;
001861b54: cbnz     w8, #0x1861b5c ;
001861b58: bl       #0x3f3f378 ;
001861b5c: mov      x0, xzr ;
001861b60: mov      x1, xzr ;
001861b64: bl       #0x1ac9f2c ; ClientSaveManager$$get_Instance
001861b68: mov      x20, x0 ;
001861b6c: mov      x0, x19 ;
001861b70: bl       #0x1861d10 ; BattlePassModule$$GetChallengeKey
001861b74: mov      x21, x0 ;
001861b78: cbnz     x20, #0x1861b80 ;
001861b7c: bl       #0x3f564f0 ;
001861b80: mov      x2, xzr ;
001861b84: mov      x0, x20 ;
001861b88: mov      x1, x21 ;
001861b8c: bl       #0x1aca04c ; ClientSaveManager$$GetIntValue
001861b90: mov      w1, w0 ;
001861b94: str      w1, [x19, #0x13c] ;
001861b98: mov      x0, x19 ;
001861b9c: bl       #0x186177c ; BattlePassModule$$CheckBattlePassChallengeOpen
001861ba0: and      w8, w0, #1 ;
001861ba4: tbnz     w8, #0, #0x1861cf0 ;
001861ba8: adrp     x8, #0x52ed000 ;
001861bac: ldr      x8, [x8, #0xaf8] ;
001861bb0: ldr      x0, [x8] ;
001861bb4: ldrb     w8, [x0, #0x10a] ;
001861bb8: tbz      w8, #0, #0x1861bc8 ;
001861bbc: ldr      w8, [x0, #0xbc] ;
001861bc0: cbnz     w8, #0x1861bc8 ;
001861bc4: bl       #0x3f3f378 ;
001861bc8: mov      x0, xzr ;
001861bcc: mov      x1, xzr ;
001861bd0: bl       #0x1bde94c ; SeasonConfigManager$$get_Instance
001861bd4: mov      x20, x0 ;
001861bd8: cbnz     x20, #0x1861be0 ;
001861bdc: bl       #0x3f564f0 ;
001861be0: mov      x1, xzr ;
001861be4: mov      x0, x20 ;
001861be8: bl       #0x1bded24 ; SeasonConfigManager$$GetAllItem
001861bec: mov      x20, x0 ;
001861bf0: cbnz     x20, #0x1861bf8 ;
001861bf4: bl       #0x3f564f0 ;
001861bf8: ldr      x20, [x20, #0x18] ;
001861bfc: cbz      x20, #0x1861cf0 ;
001861c00: adrp     x24, #0x52f6000 ;
001861c04: ldr      x24, [x24, #0x678] ;
001861c08: mov      x0, x20 ;
001861c0c: ldr      x1, [x24] ;
001861c10: bl       #0x3d51884 ; System.Collections.Generic.List<IEventSystemHandler>$$get_Count
001861c14: cmp      w0, #1 ;
001861c18: b.lt     #0x1861cf0 ;
001861c1c: ldr      x1, [x24] ;
001861c20: mov      x0, x20 ;
001861c24: bl       #0x3d51884 ; System.Collections.Generic.List<IEventSystemHandler>$$get_Count
001861c28: cmp      w0, #1 ;
001861c2c: b.lt     #0x1861cf0 ;
001861c30: adrp     x25, #0x5230000 ;
001861c34: adrp     x26, #0x5300000 ;
001861c38: adrp     x27, #0x52e6000 ;
001861c3c: ldr      x25, [x25, #0xc08] ;
001861c40: ldr      x26, [x26, #0xfa8] ;
001861c44: ldr      x27, [x27, #0x7b0] ;
001861c48: mov      w21, wzr ;
001861c4c: ldr      x2, [x25] ;
001861c50: mov      x0, x20 ;
001861c54: mov      w1, w21 ;
001861c58: bl       #0x3d5188c ; System.Collections.Generic.List<IEventSystemHandler>$$get_Item
001861c5c: mov      x22, x0 ;
001861c60: cbnz     x22, #0x1861c68 ;
001861c64: bl       #0x3f564f0 ;
001861c68: ldr      x23, [x22, #0x20] ;
001861c6c: cbnz     x23, #0x1861c74 ;
001861c70: bl       #0x3f564f0 ;
001861c74: ldr      x1, [x26] ;
001861c78: mov      x0, x23 ;
001861c7c: bl       #0x3d473f8 ; System.Collections.Generic.List<int>$$get_Count
001861c80: cmp      w0, #1 ;
001861c84: b.lt     #0x1861ccc ;
001861c88: cbnz     x22, #0x1861c90 ;
001861c8c: bl       #0x3f564f0 ;
001861c90: ldr      x23, [x22, #0x20] ;
001861c94: cbnz     x23, #0x1861c9c ;
001861c98: bl       #0x3f564f0 ;
001861c9c: ldr      x2, [x27] ;
001861ca0: mov      w1, wzr ;
001861ca4: mov      x0, x23 ;
001861ca8: bl       #0x3d47400 ; System.Collections.Generic.List<int>$$get_Item
001861cac: ldr      w8, [x19, #0x14] ;
001861cb0: cmp      w0, w8 ;
001861cb4: b.ne     #0x1861ccc ;
001861cb8: cbnz     x22, #0x1861cc0 ;
001861cbc: bl       #0x3f564f0 ;
001861cc0: ldr      w8, [x22, #0x14] ;
001861cc4: cmp      w8, #1 ;
001861cc8: b.eq     #0x1861ce8 ;
001861ccc: ldr      x1, [x24] ;
001861cd0: mov      x0, x20 ;
001861cd4: add      w21, w21, #1 ;
001861cd8: bl       #0x3d51884 ; System.Collections.Generic.List<IEventSystemHandler>$$get_Count
001861cdc: cmp      w21, w0 ;
001861ce0: b.lt     #0x1861c4c ;
001861ce4: b        #0x1861cf0 ;
001861ce8: ldr      w8, [x22, #0x10] ;
001861cec: str      w8, [x19, #0x13c] ;
001861cf0: ldr      w0, [x19, #0x13c] ;
001861cf4: ldp      x29, x30, [sp, #0x50] ;
001861cf8: ldp      x20, x19, [sp, #0x40] ;
001861cfc: ldp      x22, x21, [sp, #0x30] ;
001861d00: ldp      x24, x23, [sp, #0x20] ;
001861d04: ldp      x26, x25, [sp, #0x10] ;
001861d08: ldp      x28, x27, [sp], #0x60 ;
001861d0c: ret       ;
