"""One-time local Telegram MTProto login (Instant QR-code or Phone) for 24/7 MRKT & Tonnel sync."""

import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import qrcode
from telethon.errors import SessionPasswordNeededError

from backend.config import base_settings, runtime_config
from backend.database import db
from backend.services import auth_service
from backend.services.mtproto_auth import mtproto_auth


def _push_to_vercel() -> None:
    webapp_url = (runtime_config.webapp_url or "").strip().rstrip("/")
    if not webapp_url.startswith("https://") or "t.me" in webapp_url:
        return
    try:
        req = urllib.request.Request(
            f"{webapp_url}/api/internal/bot-sync",
            data=json.dumps(
                {
                    "user_id": runtime_config.tg_admin_chat_id or base_settings.TG_ADMIN_CHAT_ID or "owner",
                    "market_credentials": {
                        "mrkt_init_data": runtime_config.mrkt_init_data,
                        "tonnel_init_data": runtime_config.tonnel_init_data,
                    },
                }
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Bot-Sync-Signature": auth_service.get_bot_sync_signature(),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status == 200:
                print("Синхронізовано ключі з Vercel продакшном!")
    except Exception as exc:
        print(f"Примітка (Vercel sync): {exc}")


async def _login_via_qr() -> bool:
    client = await mtproto_auth._ensure_connected()
    if not client:
        print("Помилка: не вдалося підключитися до Telegram MTProto.")
        return False

    if await client.is_user_authorized():
        print("Сесія вже авторизована!")
        return True

    qr_path = ROOT / "data" / "tg_login_qr.png"
    qr_path.parent.mkdir(parents=True, exist_ok=True)

    print("\n=== ВХІД ЗА 2 СЕКУНДИ ПО QR-КОДУ (БЕЗ SMS І КОДІВ) ===")
    print("На телефоні відкрий Telegram -> Налаштування -> Пристрої -> Підключити пристрій")
    print("І наведи камеру на QR-код, який зараз відкриється на екрані!\n")

    try:
        for attempt in range(4):
            qr_login = await client.qr_login()
            qr = qrcode.QRCode(border=3, box_size=10)
            qr.add_data(qr_login.url)
            qr.make(fit=True)

            # Save crisp high-contrast PNG and open automatically on Windows
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(str(qr_path))
            if attempt == 0:
                try:
                    os.startfile(str(qr_path))
                    print(f"QR-код відкрито у вікні картинки ({qr_path})")
                except Exception:
                    qr.print_ascii(invert=True)
            else:
                print("QR-код оновлено — перевідкрий картинку або відскануй ще раз...")
                try:
                    os.startfile(str(qr_path))
                except Exception:
                    pass

            try:
                await qr_login.wait(timeout=45)
                return True
            except SessionPasswordNeededError:
                pwd = input("Введи хмарний пароль Telegram (2FA): ").strip()
                await client.sign_in(password=pwd)
                return True
            except asyncio.TimeoutError:
                print("Час дії QR вийшов, генеруємо новий...")
                continue
        return False
    finally:
        try:
            if qr_path.exists():
                qr_path.unlink()
        except Exception:
            pass


async def _login_via_phone() -> bool:
    phone = input("Введіть номер телефону Telegram (напр. +380...): ").strip()
    send_res = await mtproto_auth.send_login_code(phone)
    if not send_res.get("ok"):
        print("Помилка:", send_res.get("error"))
        return False
    if send_res.get("already_authorized"):
        return True

    code = input("Введіть код підтвердження (прийде в чат Telegram від 'Telegram'): ").strip()
    verify_res = await mtproto_auth.verify_login_code(code=code, phone=phone)
    if verify_res.get("needs_password"):
        pwd = input("Введіть хмарний пароль Telegram (2FA): ").strip()
        verify_res = await mtproto_auth.verify_login_code(code=code, password=pwd, phone=phone)
    if not verify_res.get("ok"):
        print("Помилка входу:", verify_res.get("error"))
        return False
    return True


async def main() -> None:
    await db.init()
    if not mtproto_auth.has_api_credentials():
        print("ERROR: TG_API_ID та TG_API_HASH не знайдені у .env")
        return

    use_phone = "--phone" in sys.argv
    ok = await (_login_via_phone() if use_phone else _login_via_qr())
    if not ok:
        print("Вхід не завершено. Спробуй ще раз.")
        await mtproto_auth.shutdown()
        return

    client = await mtproto_auth._ensure_connected()
    if client:
        mtproto_auth.is_authorized = bool(await client.is_user_authorized())
        me = await client.get_me()
        if me:
            uname = f"@{me.username}" if getattr(me, "username", None) else str(me.id)
            print(f"\nУСПІШНО АВТОРИЗОВАНО: {getattr(me, 'first_name', '')} ({uname})")

    print("Отримуємо свіжі живі ключі для MRKT та Tonnel...")
    ref = await mtproto_auth.refresh_all_init_data()
    print("Результат:", ref)
    _push_to_vercel()
    print("\nГОТОВО! Можеш закрити це вікно — MRKT і Tonnel тепер оновлюються автоматично!")
    await mtproto_auth.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
