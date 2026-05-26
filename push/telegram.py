"""Telegram Bot 推送模块"""
import asyncio
import httpx
import config


async def send_messages(messages: list[str]) -> bool:
    """
    将日报消息列表逐条发送到 Telegram Channel。
    DEBUG_MODE=1 时只打印到控制台，不实际发送。
    """
    if config.DEBUG_MODE:
        print("\n" + "="*60)
        print("DEBUG MODE — Telegram push simulated")
        print("="*60)
        for i, msg in enumerate(messages):
            print(f"\n--- Message {i+1}/{len(messages)} ---")
            print(msg)
        print("="*60 + "\n")
        return True

    if not config.TG_BOT_TOKEN or not config.TG_CHANNEL_ID:
        print("[WARN] TG_BOT_TOKEN or TG_CHANNEL_ID not set, skipping push")
        return False

    url = f"https://api.telegram.org/bot{config.TG_BOT_TOKEN}/sendMessage"
    success = True

    async with httpx.AsyncClient(timeout=30) as client:
        for i, msg in enumerate(messages):
            payload = {
                "chat_id":    config.TG_CHANNEL_ID,
                "text":       msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    print(f"[ERROR] Telegram send failed ({resp.status_code}): {resp.text[:200]}")
                    success = False
                else:
                    print(f"[OK] Message {i+1}/{len(messages)} sent")
                # 避免触发 TG 限流
                if i < len(messages) - 1:
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"[ERROR] Telegram exception: {e}")
                success = False

    return success
