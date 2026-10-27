"""Server-owned save-operation cooldowns; never restored from player archives."""
from dataclasses import dataclass
import math
import os


class SaveCooldownError(ValueError):
    def __init__(self, seconds):
        self.retry_after = max(1, math.ceil(seconds))
        super().__init__('Save operation cooldown: retry in %s seconds' % self.retry_after)


@dataclass(frozen=True)
class SaveLimits:
    import_seconds: int = 600
    global_import_seconds: int = 60
    export_seconds: int = 60

    @classmethod
    def from_env(cls):
        names = ('X2_SAVE_IMPORT_COOLDOWN_SECONDS',
                 'X2_SAVE_GLOBAL_IMPORT_COOLDOWN_SECONDS', 'X2_SAVE_EXPORT_COOLDOWN_SECONDS')
        values = [int(os.environ.get(n, d)) for n,d in zip(names, (600,60,60))]
        if any(v < 0 or v > 86400 for v in values):
            raise ValueError('save cooldown must be between 0 and 86400 seconds')
        return cls(*values)

    def keys(self, operation, player):
        if operation == 'import':
            return [(f'save-limit:import:{player}', self.import_seconds), ('save-limit:import:global', self.global_import_seconds)]
        return [(f'save-limit:export:{player}', self.export_seconds)]

    def check(self, db, operation, player, now):
        remaining = 0
        for key, seconds in self.keys(operation, player):
            if seconds:
                row = db.execute('SELECT value FROM server_settings WHERE key=?', (key,)).fetchone()
                if row:
                    remaining = max(remaining, float(row[0]) - now)
        if remaining > 0:
            raise SaveCooldownError(remaining)

    def record(self, db, operation, player, now):
        for key, seconds in self.keys(operation, player):
            if seconds:
                db.execute("""INSERT INTO server_settings VALUES (?,?)
                    ON CONFLICT(key) DO UPDATE SET value=CAST(MAX(CAST(value AS REAL),CAST(excluded.value AS REAL)) AS TEXT)""",
                    (key, now + seconds))
