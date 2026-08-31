import os
import tempfile
import unittest
from pathlib import Path

from orchestrator.lock import acquire_lock


class AcquireLockTests(unittest.TestCase):
    def test_acquires_when_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "build.lock"
            handle = acquire_lock(lock_path)
            assert handle is not None
            handle.close()

    def test_second_holder_in_a_child_process_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "build.lock"
            handle = acquire_lock(lock_path)
            assert handle is not None

            read_fd, write_fd = os.pipe()
            pid = os.fork()
            if pid == 0:  # child
                os.close(read_fd)
                child_handle = acquire_lock(lock_path)
                os.write(write_fd, b"1" if child_handle is None else b"0")
                os.close(write_fd)
                os._exit(0)

            os.close(write_fd)
            result = os.read(read_fd, 1)
            os.close(read_fd)
            os.waitpid(pid, 0)
            handle.close()
            self.assertEqual(result, b"1", "child process must not acquire a held lock")

    def test_lock_is_reacquirable_after_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "build.lock"
            first = acquire_lock(lock_path)
            assert first is not None
            first.close()
            second = acquire_lock(lock_path)
            assert second is not None
            second.close()


if __name__ == "__main__":
    unittest.main()
