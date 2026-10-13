; ClientSeasonProperty$$RefreshBaseProperty
; RVA [0x1ace2dc,0x1ace300), inferred from adjacent unique ScriptMethod addresses
; byte SHA256 3fe414b8fddcaf07eda28418098afbfd39865cee8e8e19c31e1f6eaa49401873
001ace2dc: stp      x20, x19, [sp, #-0x20]! ;
001ace2e0: stp      x29, x30, [sp, #0x10] ;
001ace2e4: add      x29, sp, #0x10 ;
001ace2e8: mov      x19, x0 ;
001ace2ec: bl       #0x1acd090 ; ClientSeasonProperty$$ClicentPropertyUpdate
001ace2f0: ldp      x29, x30, [sp, #0x10] ;
001ace2f4: mov      x0, x19 ;
001ace2f8: ldp      x20, x19, [sp], #0x20 ;
001ace2fc: b        #0x1accd6c ; ClientSeasonProperty$$SetAnility
