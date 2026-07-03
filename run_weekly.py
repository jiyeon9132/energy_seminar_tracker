"""
run_weekly.py
GitHub Actions에서 매주 자동 실행되는 진입점
환경변수 TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID 를 읽어서 발송합니다.
"""

import asyncio
import os
from telegram import Bot
from seminar_data import build_message


async def send():
    token      = os.environ["TELEGRAM_TOKEN"]
    channel_id = os.environ["TELEGRAM_CHANNEL_ID"]

    bot = Bot(token=token)
    msg = build_message()

    # 4096자 초과 시 분할 발송
    chunk_size = 4000
    for i in range(0, len(msg), chunk_size):
        await bot.send_message(
            chat_id=channel_id,
            text=msg[i : i + chunk_size],
        )

    print("발송 완료")


if __name__ == "__main__":
    asyncio.run(send())
