"""Attend qu'un host:port accepte TCP. Stdlib uniquement (pas d'apt/nc)."""

from __future__ import annotations

import socket
import sys
import time


def wait_for(name: str, host: str, port: int, retries: int, delay: float = 2.0) -> None:
    print(f"[wait] {name} sur {host}:{port}", flush=True)
    last: OSError | None = None
    for attempt in range(1, retries + 1):
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f"[ok] {name} disponible", flush=True)
                return
        except OSError as exc:
            last = exc
            print(f"[wait] {name} tentative {attempt}/{retries} : {exc}", flush=True)
            time.sleep(delay)
    print(f"[error] {name} indisponible après {retries} tentatives : {last}", flush=True)
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 5:
        print("usage: wait_for.py NAME HOST PORT RETRIES", file=sys.stderr)
        raise SystemExit(2)
    _name, host, port_s, retries_s = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    wait_for(_name, host, int(port_s), int(retries_s))


if __name__ == "__main__":
    main()
