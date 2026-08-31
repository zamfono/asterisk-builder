"""One host-level lock covers repository deployment, source checking,
building, and publication. A second concurrent holder gets None back and
must exit 0 without modifying state."""
import fcntl
from pathlib import Path
from typing import IO, Optional, Union


def acquire_lock(lock_path: Union[str, Path]) -> Optional[IO]:
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle
