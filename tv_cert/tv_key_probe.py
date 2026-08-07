#!/usr/bin/env python3
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
import asyncio
from androidtvremote2 import AndroidTVRemote, CannotConnect, ConnectionClosed, InvalidAuth

HOST="192.168.10.119"
CERT="/home/momo/deskclock/tv_cert/client.pem"
KEY="/home/momo/deskclock/tv_cert/client.key"
NAME="DeskClock"

KEYS = ["WAKEUP", "HOME", "POWER"]

async def send_one(k: str) -> None:
    r = AndroidTVRemote(NAME, CERT, KEY, HOST, enable_voice=False)
    try:
        await r.async_connect()
        r.send_key_command(k)
        print(f"SENT: {k}")
        await asyncio.sleep(1.2)
    except InvalidAuth:
        print("AUTH ERROR (re-pair needed)")
    except (CannotConnect, ConnectionClosed) as e:
        print(f"CONNECT FAIL: {e}")
    finally:
        r.disconnect()

async def main():
    for k in KEYS:
        print("=================================")
        print("TVをOFFにしてから Enter（次のキーを送ります）:", k)
        input()
        await send_one(k)
        print("反応（ONになった/ならない）を目視で確認してください。")

if __name__ == "__main__":
    asyncio.run(main())

