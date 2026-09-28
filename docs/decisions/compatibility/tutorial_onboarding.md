# Tutorial onboarding compatibility (2026-09-28)

**Classification: REVIVAL_COMPATIBILITY.** The original server's new-account
grant and naming policy are unavailable. Fresh registration now creates an
empty nickname and owned Hero 1003. The client selects Hero 1003 for tutorial
Section 2110001 and later targets it in Guide 21022; the original grant timing
is not proven. First naming uses opt 7 with no cost and 1–16 printable
characters. No global uniqueness rule is imposed without evidence.

`X2_SKIP_TUTORIAL=true` is an explicit development compatibility option.
Normal registration never infers a skip from account name, player ID, or DB.
Early snapshots are only repaired by an explicitly targeted, guarded command.
This decision remains provisional until full fresh-account device validation.
