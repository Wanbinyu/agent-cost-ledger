from __future__ import annotations

from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path
from typing import Iterator


@contextmanager
def packaged_data(name: str) -> Iterator[Path]:
    ref = files("agent_cost_ledger").joinpath("data").joinpath(name)
    with as_file(ref) as path:
        yield Path(path)
