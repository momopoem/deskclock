#!/usr/bin/env python3
# Copyright 2026 (C) Hiroshi Ishikawa. powered by momopoem inc.
import asyncio
from androidtvremote2 import AndroidTVRemote, InvalidAuth, CannotConnect, ConnectionClosed

HOST = "192.168.10.119"
CERT = "/home/momo/deskclock/tv_cert/client.pem"
KEY  = "/home/momo/deskclock/tv_cert/client.key"
NAME = "DeskClock"

async def main():
    remote = AndroidTVRemote(NAME, CERT, KEY, HOST, enable_voice=False)
    try:
        await remote.async_connect()
        remote.send_key_command("POWER")
        print("SENT: POWER")
    except InvalidAuth:
        print("認証エラー（ペアリングやり直しが必要）")
    except (CannotConnect, ConnectionClosed) as e:
        print("接続失敗:", e)
    finally:
        remote.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

