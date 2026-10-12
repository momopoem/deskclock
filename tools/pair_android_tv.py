#!/usr/bin/env python3
"""Pair this host with an Android/Google TV Remote v2 service.

Run on the Desk Side Clock Raspberry Pi while the television is on.  The
generated private key and certificate stay outside the repository by default.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from androidtvremote2 import AndroidTVRemote, CannotConnect, ConnectionClosed, InvalidAuth


async def pair(host: str, cert: Path, key: Path, name: str) -> None:
    cert.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    remote = AndroidTVRemote(name, str(cert), str(key), host, enable_voice=False)
    try:
        await remote.async_generate_cert_if_missing()
        # androidtvremote2 creates these files with the process umask.  The
        # private key is authentication material, so never leave it readable
        # by other local users.
        cert.chmod(0o600)
        key.chmod(0o600)
        await remote.async_start_pairing()
        code = input("テレビに表示された6桁のコードを入力: ").strip()
        await remote.async_finish_pairing(code)
        print(f"PAIRING_OK cert={cert}")
    except InvalidAuth as exc:
        raise SystemExit(f"PAIRING_REJECTED: {exc}") from exc
    except (CannotConnect, ConnectionClosed) as exc:
        raise SystemExit(f"PAIRING_CONNECTION_ERROR: {exc}") from exc
    finally:
        remote.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True, help="テレビの固定IPアドレスまたはホスト名")
    parser.add_argument("--cert", type=Path, default=Path.home() / ".config/deskclock/tv/client.pem")
    parser.add_argument("--key", type=Path, default=Path.home() / ".config/deskclock/tv/client.key")
    parser.add_argument("--name", default="Desk Side Clock")
    args = parser.parse_args()
    asyncio.run(pair(args.host, args.cert.expanduser(), args.key.expanduser(), args.name))


if __name__ == "__main__":
    main()
