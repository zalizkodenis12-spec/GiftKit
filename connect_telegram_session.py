"""One-time local Telegram MTProto login script to activate 24/7 auto-refresh for MRKT & Tonnel."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import runtime_config
from backend.database import db
from backend.services.mtproto_auth import mtproto_auth


async def main() -> None:
    await db.init()
    if not mtproto_auth.has_api_credentials():
        print("ERROR: TG_API_ID та TG_API_HASH не знайдені у .env")
        return

    print("Підключення до офіційного Telegram MTProto API...")
    phone = input("Введіть номер телефону Telegram (напр. +380...): ").strip()
    send_res = await mtproto_auth.send_login_code(phone)
    if not send_res.get("ok"):
        print("Помилка:", send_res.get("error"))
        return

    if send_res.get("already_authorized"):
        print("Сесія вже авторизована:", send_res.get("account"))
        print("Оновлення ключів:", send_res.get("refresh"))
        return

    code = input("Введіть код підтвердження, який прийшов у Telegram: ").strip()
    verify_res = await mtproto_auth.verify_login_code(code=code, phone=phone)
    if verify_res.get("needs_password"):
        pwd = input("Введіть хмарний пароль Telegram (2FA): ").strip()
        verify_res = await mtproto_auth.verify_login_code(code=code, password=pwd, phone=phone)

    if verify_res.get("ok"):
        print("УСПІШНО! Авторизовано:", verify_res.get("account"))
        print("Оновлено MRKT & Tonnel:", verify_res.get("refresh"))
    else:
        print("Помилка входу:", verify_res.get("error"))

    await mtproto_auth.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
