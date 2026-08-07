#!/usr/bin/env python3
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
import asyncio
from androidtvremote2 import AndroidTVRemote, InvalidAuth, ConnectionClosed, CannotConnect

HOST = "192.168.10.119"
CERT = "/home/momo/deskclock/tv_cert/client.pem"
KEY  = "/home/momo/deskclock/tv_cert/client.key"
NAME = "DeskClock"

async def main():
    remote = AndroidTVRemote(NAME, CERT, KEY, HOST, enable_voice=False)

    try:
        await remote.async_start_pairing()
    except CannotConnect as e:
        print("ペアリング開始に失敗しました（接続不可）:", e)
        return

    while True:
        code = input("TVに出たペアリングコード(6桁)を入力: ").strip()
        if not code:
            print("空です。もう一度。")
            continue

        try:
            await remote.async_finish_pairing(code)
            print("PAIR OK")
            break
        except InvalidAuth:
            print("コードが違うようです。もう一度。")
        except ConnectionClosed:
            print("接続が切れました。ペアリングを最初からやり直します。")
            await remote.async_start_pairing()

    remote.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

