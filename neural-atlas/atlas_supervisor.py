"""User-session supervisor. No model imports, GPU access, or canonical writes."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request


@contextmanager
def instance_lock(root):
    path = Path(root) / "data/supervisor.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


class Supervisor:
    def __init__(self, root, probe=None, launch=None, clock=time.monotonic):
        self.root = Path(root)
        self.config = json.loads((self.root / "config.json").read_text(encoding="utf-8-sig"))
        self.clock = clock
        self.probe = probe or self.probe_worker
        self.launch = launch or self.launch_worker
        self.next_launch = 0
        self.last_event = None

    def probe_worker(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(f"http://127.0.0.1:{self.config['port']}/api/status", timeout=5) as response:
                value = json.load(response)
            if value.get("app") != "neural-atlas":
                return {"state": "foreign_listener"}
            return {"state": "healthy", "worker_pid": value.get("pid"), "paused": value.get("paused"), "phase": value.get("runtime", {}).get("phase")}
        except urllib.error.HTTPError:
            return {"state": "foreign_or_unhealthy_listener"}
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, ConnectionRefusedError) or getattr(reason, "winerror", None) == 10061 or getattr(reason, "errno", None) in {61, 111, 10061}:
                return {"state": "missing"}
            return {"state": "unreachable", "error": str(reason)[:200]}
        except (OSError, ValueError, TypeError) as exc:
            return {"state": "unreachable", "error": str(exc)[:200]}

    def saved_pause(self):
        path = self.root / "data/atlas.sqlite3"
        if not path.exists():
            return False
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
        try:
            row = db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()
            return json.loads(row[0]) if row else False
        finally:
            db.close()

    def launch_worker(self):
        python = Path(self.config["python"])
        pythonw = python.with_name("pythonw.exe")
        executable = pythonw if pythonw.exists() else python
        if not executable.is_file() or not (self.root / "atlas.py").is_file():
            raise ValueError("Installed atlas runtime is unavailable; retrying later")
        data = self.root / "data"
        with (data / "server.log").open("ab") as stdout, (data / "server.err").open("ab") as stderr:
            process = subprocess.Popen([str(executable), "-B", str(self.root / "atlas.py"), "serve", "--root", str(self.root)],
                                       cwd=self.root, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, close_fds=True)
        return process.pid

    def cycle(self):
        result = self.probe()
        if result["state"] == "missing":
            try:
                if self.saved_pause():
                    result = {"state": "intentional_stop_or_pause", "restart_suppressed": True}
                elif self.clock() < self.next_launch:
                    result = {"state": "starting", "retry_after_seconds": round(self.next_launch - self.clock())}
                else:
                    # A cold model load is slower than the web server. Prevent launch storms.
                    self.next_launch = self.clock() + 120
                    pid = self.launch()
                    result = {"state": "started_worker", "launcher_pid": pid}
            except Exception as exc:
                self.next_launch = self.clock() + 120
                result = {"state": "launch_error", "error": str(exc)[:300]}
        result.update(supervisor_pid=os.getpid(), checked_at=dt.datetime.now(dt.timezone.utc).isoformat(), interval_seconds=30)
        data = self.root / "data"
        data.mkdir(parents=True, exist_ok=True)
        temp = data / "supervisor-status.tmp"
        temp.write_text(json.dumps(result, indent=2), encoding="utf-8")
        os.replace(temp, data / "supervisor-status.json")
        event = {k: v for k, v in result.items() if k not in {"checked_at", "retry_after_seconds"}}
        if event != self.last_event:
            log = data / "supervisor.log"
            if log.exists() and log.stat().st_size > 1024 * 1024:
                os.replace(log, data / "supervisor.previous.log")
            with log.open("a", encoding="utf-8") as output:
                output.write(json.dumps(result) + "\n")
            self.last_event = event
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).parent))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    from atlas import low_priority
    low_priority()
    try:
        with instance_lock(root):
            supervisor = Supervisor(root)
            while True:
                try:
                    result = supervisor.cycle()
                except Exception as exc:
                    # Transient vault/volume/file access must not permanently end startup recovery.
                    result = {"state": "check_error", "error": str(exc)[:250]}
                if args.once:
                    print(json.dumps(result))
                    break
                time.sleep(30)
    except OSError:
        # Another registered/manual supervisor already owns the process lock.
        return


if __name__ == "__main__":
    main()
