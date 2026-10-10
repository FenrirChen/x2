"""College alchemy static tables still shared by the other College services.

The alchemy feature itself (messages 590..605 / 729..732 / 824..827 plus the 617
push) now lives in :mod:`x2server.player.alchemy` on its own three tables.  What
remains here is only ``rules()`` — the ``data/college_alchemy_rules.json`` view
that ``college_jobs`` (explore speed-up / element rewards) and ``college_upgrade``
(acceleration cards) still read for their own parameters.
"""
from functools import lru_cache
from importlib.resources import files
import json


@lru_cache(maxsize=1)
def rules():
    return json.loads(files('x2server').joinpath('data/college_alchemy_rules.json').read_text(encoding='utf8'))
