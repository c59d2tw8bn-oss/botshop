# ═══════════════════════════════════════════════════════════════
#  BOT SHOP LIÊN QUÂN (ASYNC) — Bản đã gỡ bỏ Tài Xỉu / hệ thống xu
#  Cài thư viện: pip install aiogram==3.13.1 sqlalchemy==2.0.36 aiosqlite==0.20.0 aiofiles==24.1.0 aiohttp
# ═══════════════════════════════════════════════════════════════

import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  # Đặt token qua biến môi trường, KHÔNG hardcode trong code
ADMIN_IDS = [7936179657]  # ID Telegram Admin

import asyncio
import enum
import functools
import logging
import re as _re
import secrets
import string
import sys
import uuid
import random
from datetime import datetime, timedelta

import aiofiles
from aiohttp import web
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    KeyboardButton,
    Message,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    select,
    text as sa_text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    selectinload,
)

# ── Cấu hình Shop ──────────────────────────────────────────────────────────────
ACCOUNT_PRICE = 350  # VNĐ mỗi acc
MIN_ORDER_QTY = 1  # Số lượng tối thiểu
CHECKER_LINK = "t.me/tretrauchecker_bot?start=_tgr_8UulJtkyZjE1"

# ── Cấu hình tính năng Premium ───────────────────────────────────────────────
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")  # dùng để tạo link giới thiệu, vd: MyShopBot
CHECKIN_REWARD = 500          # điểm thưởng điểm danh mỗi ngày
CHECKIN_STREAK_BONUS = 100    # điểm cộng thêm mỗi ngày giữ streak (tối đa nhân 7)
REFERRAL_REWARD = 3000        # VNĐ thưởng cho người mời khi giới thiệu nạp tiền lần đầu
REFERRAL_MIN_DEPOSIT = 20000  # Số tiền nạp tối thiểu lần đầu để tính thưởng giới thiệu
POINTS_PER_VND_SPENT = 1      # số điểm nhận được trên mỗi 1.000 VNĐ chi tiêu (mua acc)
MEMBERSHIP_TIERS = [
    (0, "🥉 Đồng"),
    (200_000, "🥈 Bạc"),
    (1_000_000, "🥇 Vàng"),
    (5_000_000, "💎 Kim Cương"),
]
HEARTBEAT_INTERVAL_SEC = 60
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 1.5

# ── Cấu hình Thanh Toán Tự Động (SePay) ──────────────────────────────────────
# Đăng ký & liên kết tài khoản ngân hàng tại https://my.sepay.vn, lấy API Key ở menu Tích hợp Webhooks.
SEPAY_API_KEY = os.environ.get("SEPAY_API_KEY", "")          # API Key cấu hình xác thực webhook bên SePay
SEPAY_BANK_ACCOUNT = os.environ.get("SEPAY_BANK_ACCOUNT", "")  # Số tài khoản MB Bank nhận tiền
SEPAY_BANK_CODE = os.environ.get("SEPAY_BANK_CODE", "MBBank")  # Mã ngân hàng dùng để tạo QR VietQR (SePay quy ước)
DEPOSIT_CODE_PREFIX = "NAP"   # Tiền tố mã nạp tiền, khách phải ghi đúng vào nội dung chuyển khoản
DEPOSIT_EXPIRE_MINUTES = 30   # Phút hết hạn của 1 yêu cầu nạp tiền tự động chưa thanh toán

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
QR_IMAGE_PATH = os.path.join(UPLOADS_DIR, "qr_current.jpg")
# Đặt chuỗi kết nối DB qua biến môi trường, KHÔNG hardcode trong code
DATABASE_URL = os.environ.get("DATABASE_URL", "")

MENU_BUTTONS = {
    "🟢 Bot Đang Chạy 24/7", "🏠 Trang Chủ", "🛒 Mua Acc", "💳 Nạp Tiền", "👤 Tài Khoản", "📦 Đơn Hàng", "☎ Hỗ Trợ",
    "🎁 Giftcode", "📅 Điểm Danh", "🔗 Giới Thiệu", "❓ FAQ",
    "📊 Dashboard", "📥 Import TXT", "📦 Xem Kho", "📊 Thống Kê", "💰 Cộng Tiền", "💸 Trừ Tiền",
    "📷 Đổi QR", "📥 Bill Chờ", "📢 Broadcast", "🚫 Ban User",
    "✅ Unban User", "🗑 Xóa Account", "🧹 Dọn Acc Rác", "📤 Export Chưa Bán", "📤 Export Đã Bán", "🔙 Menu Chính",
    "🎫 Tạo Giftcode", "🛠 Chế Độ Bảo Trì", "📣 Đặt Banner", "🏆 Top Nạp/Mua",
}

# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOGS_DIR, "bot.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ── Database ──────────────────────────────────────────────────────────────────
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class AccountStatus(str, enum.Enum):
    available = "available"
    sold = "sold"

class OrderStatus(str, enum.Enum):
    completed = "completed"
    cancelled = "cancelled"

class DepositStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

class TaskCode(str, enum.Enum):
    join_group = "join_group"
    join_channel = "join_channel"
    invite_friend = "invite_friend"
    daily_checkin = "daily_checkin"

# ── Models ────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fullname: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    # ── Cột mới cho hệ thống Premium (an toàn với DB cũ nhờ migration ALTER TABLE) ──
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    referred_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # telegram_id người giới thiệu
    referral_rewarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_checkin_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    checkin_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="user")
    deposits: Mapped[list["Deposit"]] = relationship("Deposit", back_populates="user")

class Account(Base):
    # Đổi sang v4 và chuyển kiểu dữ liệu username/password sang Text để nuốt trọn chuỗi dài không lo lỗi quá ký tự
    __tablename__ = "accounts_v4"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AccountStatus] = mapped_column(Enum(AccountStatus), nullable=False, default=AccountStatus.available)
    order_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("orders.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    sold_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    skin_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # Số skin (từ checker)
    tuong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Số tướng (từ checker)
    order: Mapped["Order|None"] = relationship("Order", back_populates="accounts")

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), nullable=False, default=OrderStatus.completed)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    user: Mapped["User"] = relationship("User", back_populates="orders")
    accounts: Mapped[list["Account"]] = relationship("Account", back_populates="order")

class Deposit(Base):
    __tablename__ = "deposits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    bill_image: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[DepositStatus] = mapped_column(Enum(DepositStatus), nullable=False, default=DepositStatus.pending)
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ── Cột mới phục vụ thanh toán tự động qua SePay Webhook ──
    code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)          # Mã nội dung CK, vd NAP000123
    sepay_txn_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)  # ID giao dịch SePay, chống xử lý trùng
    auto_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)      # True nếu được duyệt tự động qua webhook
    user: Mapped["User"] = relationship("User", back_populates="deposits")

class GiftCode(Base):
    __tablename__ = "giftcodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # VNĐ cộng vào số dư
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

class GiftCodeRedemption(Base):
    __tablename__ = "giftcode_redemptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    giftcode_id: Mapped[int] = mapped_column(Integer, ForeignKey("giftcodes.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

class Voucher(Base):
    """Voucher giảm giá áp dụng khi mua acc (giảm theo % hoặc số tiền cố định)."""
    __tablename__ = "vouchers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    discount_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

class VoucherRedemption(Base):
    __tablename__ = "voucher_redemptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    voucher_id: Mapped[int] = mapped_column(Integer, ForeignKey("vouchers.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

class Setting(Base):
    """Bảng key-value dùng cho banner thông báo, chế độ bảo trì, v.v."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migration: thêm cột skin_count / tuong_count nếu chưa có (an toàn cho DB cũ)
        for col in ("skin_count", "tuong_count"):
            try:
                await conn.execute(
                    sa_text(f"ALTER TABLE accounts_v4 ADD COLUMN IF NOT EXISTS {col} INTEGER NOT NULL DEFAULT 0")
                )
            except Exception:
                pass  # Một số driver báo lỗi nếu cột đã tồn tại – bỏ qua

        # Migration: thêm cột mới cho hệ thống Premium trên bảng users (an toàn cho DB cũ)
        user_int_cols = {"points": "INTEGER NOT NULL DEFAULT 0", "checkin_streak": "INTEGER NOT NULL DEFAULT 0"}
        for col, coltype in user_int_cols.items():
            try:
                await conn.execute(sa_text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {coltype}"))
            except Exception:
                pass
        try:
            await conn.execute(sa_text("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT"))
        except Exception:
            pass
        try:
            await conn.execute(sa_text("ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_rewarded BOOLEAN NOT NULL DEFAULT FALSE"))
        except Exception:
            pass
        try:
            await conn.execute(sa_text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_checkin_date VARCHAR(10)"))
        except Exception:
            pass
        # Migration: cột mới trên bảng deposits cho thanh toán tự động SePay
        try:
            await conn.execute(sa_text("ALTER TABLE deposits ADD COLUMN IF NOT EXISTS code VARCHAR(32)"))
        except Exception:
            pass
        try:
            await conn.execute(sa_text("ALTER TABLE deposits ADD COLUMN IF NOT EXISTS sepay_txn_id VARCHAR(64)"))
        except Exception:
            pass
        try:
            await conn.execute(sa_text("ALTER TABLE deposits ADD COLUMN IF NOT EXISTS auto_confirmed BOOLEAN NOT NULL DEFAULT FALSE"))
        except Exception:
            pass
    logger.info("Database initialized")

# ── Services ──────────────────────────────────────────────────────────────────
async def get_or_create_user(session, telegram_id, username, fullname, is_admin=False, referred_by=None):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        ref = referred_by if (referred_by and referred_by != telegram_id) else None
        user = User(telegram_id=telegram_id, username=username, fullname=fullname, is_admin=is_admin, referred_by=ref)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        changed = False
        if user.username != username: user.username = username; changed = True
        if user.fullname != fullname: user.fullname = fullname; changed = True
        if changed:
            await session.commit()
            await session.refresh(user)
    return user

async def get_user_by_telegram_id(session, telegram_id):
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return r.scalar_one_or_none()

async def get_user_by_id(session, user_id):
    r = await session.execute(select(User).where(User.id == user_id))
    return r.scalar_one_or_none()

async def add_balance(session, user_id, amount):
    user = await get_user_by_id(session, user_id)
    if user is None: return None
    user.balance += amount
    await session.commit()
    await session.refresh(user)
    return user

async def adjust_balance_by_telegram_id(session, telegram_id, amount):
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None: return None
    user.balance += amount
    if user.balance < 0: user.balance = 0
    await session.commit()
    await session.refresh(user)
    return user

async def ban_user(session, telegram_id):
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = r.scalar_one_or_none()
    if user is None: return False
    user.is_banned = True
    await session.commit()
    return True

async def unban_user(session, telegram_id):
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = r.scalar_one_or_none()
    if user is None: return False
    user.is_banned = False
    await session.commit()
    return True

async def get_all_users(session):
    r = await session.execute(select(User)); return list(r.scalars().all())

async def get_available_count(session):
    # Chỉ đếm acc có thể bán được (có skin hoặc tướng > 0)
    r = await session.execute(
        select(func.count()).where(
            Account.status == AccountStatus.available,
            (Account.skin_count + Account.tuong_count) > 0
        )
    )
    return r.scalar_one()

async def get_trash_count(session):
    r = await session.execute(
        select(func.count()).where(
            Account.status == AccountStatus.available,
            Account.skin_count == 0,
            Account.tuong_count == 0
        )
    )
    return r.scalar_one()

async def delete_trash_accounts(session):
    r = await session.execute(
        select(Account).where(
            Account.status == AccountStatus.available,
            Account.skin_count == 0,
            Account.tuong_count == 0
        )
    )
    accs = list(r.scalars().all())
    for a in accs:
        await session.delete(a)
    await session.commit()
    return len(accs)

async def get_sold_count(session):
    r = await session.execute(select(func.count()).where(Account.status == AccountStatus.sold)); return r.scalar_one()

async def get_total_count(session):
    r = await session.execute(select(func.count()).select_from(Account)); return r.scalar_one()

async def pick_random_accounts(session, quantity):
    # Chỉ lấy acc ngon (có skin hoặc tướng > 0), ưu tiên acc nhiều skin + tướng nhất
    pool_size = max(quantity * 5, 200)
    r = await session.execute(
        select(Account)
        .where(
            Account.status == AccountStatus.available,
            (Account.skin_count + Account.tuong_count) > 0
        )
        .with_for_update()
        .order_by((Account.skin_count + Account.tuong_count).desc())
        .limit(pool_size)
    )
    pool = list(r.scalars().all())
    if len(pool) <= quantity:
        return pool
    weights = [(a.skin_count + a.tuong_count + 1) for a in pool]
    chosen = []
    chosen_ids = set()
    attempts = 0
    while len(chosen) < quantity and attempts < quantity * 20:
        attempts += 1
        pick = random.choices(pool, weights=weights, k=1)[0]
        if pick.id not in chosen_ids:
            chosen.append(pick)
            chosen_ids.add(pick.id)
    if len(chosen) < quantity:
        for a in pool:
            if a.id not in chosen_ids:
                chosen.append(a)
            if len(chosen) >= quantity:
                break
    return chosen

async def mark_accounts_sold(session, accounts, order_id):
    now = datetime.utcnow()
    for acc in accounts:
        acc.status = AccountStatus.sold
        acc.order_id = order_id
        acc.sold_at = now
    await session.commit()

# ── Hàm Import Đã Được Gia Cố Tối Đa ──────────────────────────────────────────
def _parse_checker_line(line: str):
    """
    Hỗ trợ nhiều format checker:

    Format 1 (FINAL/checker mới):
      FINAL = username:password | Name: ... | Tướng: 105 | Skin: 258 | Ban: No | ...

    Format 2 (checker cũ UID):
      username:password|UID=...|...|Skin=222|Tướng=95|BAN=NO|...

    Format đơn giản:
      username:password  hoặc  username|password

    Trả về (username, password, skin_count, tuong_count, is_banned)
    hoặc None nếu không parse được.
    """
    stripped = line.strip()
    if stripped.upper().startswith("FINAL"):
        eq = stripped.find("=")
        if eq != -1:
            stripped = stripped[eq + 1:].strip()

    info_part = ""
    uid_sep = stripped.find("|UID=")
    if uid_sep != -1:
        cred_part = stripped[:uid_sep].strip()
        info_part = stripped[uid_sep:]
    elif " | " in stripped:
        first_pipe = stripped.find(" | ")
        cred_part = stripped[:first_pipe].strip()
        info_part = stripped[first_pipe:]
    else:
        cred_part = stripped

    if ":" in cred_part:
        uname, pwd = cred_part.split(":", 1)
    elif "|" in cred_part:
        uname, pwd = cred_part.split("|", 1)
    else:
        return None

    uname = uname.strip()
    pwd = pwd.strip()
    if not uname or not pwd:
        return None

    skin_count = 0
    tuong_count = 0
    is_banned = False

    if info_part:
        m_skin = _re.search(r"[|\s]Skin\s*[=:]\s*(\d+)", info_part)
        m_tuong = _re.search(r"[|\s]Tướng\s*[=:]\s*(\d+)", info_part)
        m_ban = _re.search(r"[|\s]Ban\s*[=:]\s*(Yes|No|YES|NO)", info_part, _re.IGNORECASE)
        if m_skin:
            skin_count = int(m_skin.group(1))
        if m_tuong:
            tuong_count = int(m_tuong.group(1))
        if m_ban:
            is_banned = m_ban.group(1).upper() in ("YES", "Y")

    return uname, pwd, skin_count, tuong_count, is_banned


async def import_accounts(session, lines):
    stats = {
        "total": 0,
        "imported": 0,
        "duplicates": 0,
        "invalid": 0,
        "filtered_banned": 0,
        "filtered_empty": 0,
    }

    r_all = await session.execute(select(Account.username))
    existing_unames = set(r_all.scalars().all())

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        stats["total"] += 1

        parsed = _parse_checker_line(line)
        if parsed is None:
            stats["invalid"] += 1
            continue

        uname, pwd, skin_count, tuong_count, is_banned = parsed

        if is_banned:
            stats["filtered_banned"] += 1
            continue
        if skin_count == 0 and tuong_count == 0:
            stats["filtered_empty"] += 1
            continue

        if uname in existing_unames:
            stats["duplicates"] += 1
            continue

        session.add(Account(
            username=uname,
            password=pwd,
            status=AccountStatus.available,
            skin_count=skin_count,
            tuong_count=tuong_count,
        ))
        existing_unames.add(uname)
        stats["imported"] += 1

    await session.commit()
    return stats

async def get_unsold_accounts(session):
    r = await session.execute(select(Account).where(Account.status == AccountStatus.available)); return list(r.scalars().all())

async def get_sold_accounts(session):
    r = await session.execute(select(Account).where(Account.status == AccountStatus.sold)); return list(r.scalars().all())

async def delete_account_by_username(session, username):
    r = await session.execute(select(Account).where(Account.username == username))
    acc = r.scalar_one_or_none()
    if acc is None: return False
    await session.delete(acc)
    await session.commit()
    return True

async def create_order(session, user_id, quantity, price, file_name):
    order = Order(user_id=user_id, quantity=quantity, price=price, status=OrderStatus.completed, file_name=file_name)
    session.add(order)
    await session.flush()
    return order

async def get_user_orders(session, user_id, limit=20):
    r = await session.execute(select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()).limit(limit))
    return list(r.scalars().all())

async def get_all_orders(session, limit=50):
    r = await session.execute(select(Order).order_by(Order.created_at.desc()).limit(limit))
    return list(r.scalars().all())

async def create_deposit(session, user_id, amount, bill_image=None):
    dep = Deposit(user_id=user_id, amount=amount, bill_image=bill_image, status=DepositStatus.pending)
    session.add(dep)
    await session.flush()  # cần dep.id trước khi sinh mã
    dep.code = f"{DEPOSIT_CODE_PREFIX}{dep.id:06d}"
    await session.commit()
    await session.refresh(dep)
    return dep

async def get_deposit_by_id(session, deposit_id):
    r = await session.execute(select(Deposit).options(selectinload(Deposit.user)).where(Deposit.id == deposit_id))
    return r.scalar_one_or_none()

async def get_pending_deposit_by_code(session, code):
    """Tìm yêu cầu nạp tiền đang chờ khớp với mã trong nội dung chuyển khoản (dùng cho webhook tự động)."""
    r = await session.execute(
        select(Deposit).options(selectinload(Deposit.user))
        .where(Deposit.status == DepositStatus.pending, Deposit.code == code)
        .order_by(Deposit.created_at.desc())
    )
    return r.scalar_one_or_none()

def build_vietqr_url(amount, content):
    """Sinh URL ảnh QR VietQR động qua SePay — không cần admin upload QR thủ công."""
    from urllib.parse import quote
    return (
        f"https://qr.sepay.vn/img?acc={SEPAY_BANK_ACCOUNT}&bank={SEPAY_BANK_CODE}"
        f"&amount={amount}&des={quote(content)}"
    )

async def auto_confirm_deposit(session, deposit_id, sepay_txn_id):
    """Duyệt tự động một yêu cầu nạp tiền khi webhook SePay khớp mã & số tiền."""
    dep = await get_deposit_by_id(session, deposit_id)
    if dep is None or dep.status != DepositStatus.pending:
        return None
    dep.status = DepositStatus.approved
    dep.approved_at = datetime.utcnow()
    dep.auto_confirmed = True
    dep.sepay_txn_id = str(sepay_txn_id)
    await session.commit()
    await session.refresh(dep)
    return dep

async def approve_deposit(session, deposit_id, admin_tg_id):
    dep = await get_deposit_by_id(session, deposit_id)
    if dep is None or dep.status != DepositStatus.pending: return None
    dep.status = DepositStatus.approved
    dep.admin_id = admin_tg_id
    dep.approved_at = datetime.utcnow()
    await session.commit()
    await session.refresh(dep)
    return dep

async def reject_deposit(session, deposit_id, admin_tg_id):
    dep = await get_deposit_by_id(session, deposit_id)
    if dep is None or dep.status != DepositStatus.pending: return None
    dep.status = DepositStatus.rejected
    dep.admin_id = admin_tg_id
    dep.approved_at = datetime.utcnow()
    await session.commit()
    await session.refresh(dep)
    return dep

async def get_pending_deposits(session):
    r = await session.execute(select(Deposit).options(selectinload(Deposit.user)).where(Deposit.status == DepositStatus.pending).order_by(Deposit.created_at.asc()))
    return list(r.scalars().all())


# ── Điểm thưởng / Điểm danh / Hạng thành viên ────────────────────────────────
def get_membership_tier(total_spent: int) -> str:
    tier_name = MEMBERSHIP_TIERS[0][1]
    for threshold, name in MEMBERSHIP_TIERS:
        if total_spent >= threshold:
            tier_name = name
    return tier_name

async def get_user_total_spent(session, user_id) -> int:
    r = await session.execute(
        select(func.coalesce(func.sum(Order.price), 0)).where(Order.user_id == user_id, Order.status == OrderStatus.completed)
    )
    return int(r.scalar_one())

async def get_user_total_deposited(session, user_id) -> int:
    r = await session.execute(
        select(func.coalesce(func.sum(Deposit.amount), 0)).where(Deposit.user_id == user_id, Deposit.status == DepositStatus.approved)
    )
    return int(r.scalar_one())

async def add_points(session, user_id, amount):
    user = await get_user_by_id(session, user_id)
    if user is None:
        return None
    user.points = max(0, user.points + amount)
    await session.commit()
    await session.refresh(user)
    return user

async def do_daily_checkin(session, user):
    """Trả về (success, reward_points, streak) — chặn nếu đã điểm danh hôm nay."""
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    if user.last_checkin_date == today_str:
        return False, 0, user.checkin_streak
    yesterday_str = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    streak = user.checkin_streak + 1 if user.last_checkin_date == yesterday_str else 1
    streak_bonus = min(streak, 7) * CHECKIN_STREAK_BONUS
    reward = CHECKIN_REWARD + streak_bonus
    user.last_checkin_date = today_str
    user.checkin_streak = streak
    user.points += reward
    await session.commit()
    await session.refresh(user)
    return True, reward, streak

async def get_referral_stats(session, telegram_id):
    r = await session.execute(select(func.count()).where(User.referred_by == telegram_id))
    total_invited = r.scalar_one()
    r2 = await session.execute(select(func.count()).where(User.referred_by == telegram_id, User.referral_rewarded == True))  # noqa: E712
    rewarded = r2.scalar_one()
    return {"total_invited": total_invited, "rewarded": rewarded, "total_earned": rewarded * REFERRAL_REWARD}

async def maybe_reward_referrer(session, bot, deposit_user: User, deposit_amount: int):
    """Gọi sau khi duyệt nạp tiền — thưởng người giới thiệu nếu đây là lần nạp đầu tiên đạt mức tối thiểu."""
    if not deposit_user.referred_by or deposit_user.referral_rewarded:
        return None
    if deposit_amount < REFERRAL_MIN_DEPOSIT:
        return None
    referrer = await get_user_by_telegram_id(session, deposit_user.referred_by)
    if referrer is None:
        return None
    referrer.balance += REFERRAL_REWARD
    deposit_user.referral_rewarded = True
    await session.commit()
    try:
        await bot.send_message(
            referrer.telegram_id,
            f"🎉 <b>Bạn nhận thưởng giới thiệu!</b>\n\n"
            f"👤 Bạn bè <b>{deposit_user.fullname}</b> vừa nạp tiền lần đầu.\n"
            f"💵 Thưởng: <b>{REFERRAL_REWARD:,} VNĐ</b>\n"
            f"💰 Số dư mới: <b>{referrer.balance:,} VNĐ</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    return referrer

# ── Giftcode ──────────────────────────────────────────────────────────────────
def _generate_code(prefix="GIFT", length=8):
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-{''.join(secrets.choice(chars) for _ in range(length))}"

async def create_giftcode(session, amount, max_uses=1, code=None):
    code = code or _generate_code("GIFT")
    gc = GiftCode(code=code, amount=amount, max_uses=max_uses)
    session.add(gc)
    await session.commit()
    await session.refresh(gc)
    return gc

async def redeem_giftcode(session, code, user: User):
    r = await session.execute(select(GiftCode).where(GiftCode.code == code.strip().upper()))
    gc = r.scalar_one_or_none()
    if gc is None or not gc.is_active:
        return "not_found", None
    if gc.used_count >= gc.max_uses:
        return "exhausted", None
    r2 = await session.execute(
        select(GiftCodeRedemption).where(GiftCodeRedemption.giftcode_id == gc.id, GiftCodeRedemption.user_id == user.id)
    )
    if r2.scalar_one_or_none() is not None:
        return "already_used", None
    gc.used_count += 1
    session.add(GiftCodeRedemption(giftcode_id=gc.id, user_id=user.id))
    user.balance += gc.amount
    await session.commit()
    await session.refresh(user)
    return "ok", gc.amount

# ── Voucher (giảm giá khi mua acc) ───────────────────────────────────────────
async def create_voucher(session, discount_percent, max_uses=1, code=None):
    code = code or _generate_code("SALE")
    v = Voucher(code=code, discount_percent=discount_percent, max_uses=max_uses)
    session.add(v)
    await session.commit()
    await session.refresh(v)
    return v

async def validate_voucher(session, code, user: User):
    r = await session.execute(select(Voucher).where(Voucher.code == code.strip().upper()))
    v = r.scalar_one_or_none()
    if v is None or not v.is_active or v.used_count >= v.max_uses:
        return None
    r2 = await session.execute(
        select(VoucherRedemption).where(VoucherRedemption.voucher_id == v.id, VoucherRedemption.user_id == user.id)
    )
    if r2.scalar_one_or_none() is not None:
        return None
    return v

async def consume_voucher(session, voucher: Voucher, user: User):
    voucher.used_count += 1
    session.add(VoucherRedemption(voucher_id=voucher.id, user_id=user.id))
    await session.commit()

# ── Settings (banner thông báo / chế độ bảo trì) ─────────────────────────────
async def get_setting(session, key, default=""):
    r = await session.execute(select(Setting).where(Setting.key == key))
    row = r.scalar_one_or_none()
    return row.value if row else default

async def set_setting(session, key, value):
    r = await session.execute(select(Setting).where(Setting.key == key))
    row = r.scalar_one_or_none()
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
    await session.commit()

async def is_maintenance_mode(session) -> bool:
    return (await get_setting(session, "maintenance_mode", "0")) == "1"

# ── Thống kê nâng cao cho Admin Dashboard ────────────────────────────────────
async def get_top_depositors(session, limit=5):
    r = await session.execute(
        select(User, func.sum(Deposit.amount).label("total"))
        .join(Deposit, Deposit.user_id == User.id)
        .where(Deposit.status == DepositStatus.approved)
        .group_by(User.id)
        .order_by(func.sum(Deposit.amount).desc())
        .limit(limit)
    )
    return r.all()

async def get_top_buyers(session, limit=5):
    r = await session.execute(
        select(User, func.sum(Order.price).label("total"))
        .join(Order, Order.user_id == User.id)
        .where(Order.status == OrderStatus.completed)
        .group_by(User.id)
        .order_by(func.sum(Order.price).desc())
        .limit(limit)
    )
    return r.all()

async def get_orders_today_count_and_revenue(session):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    r = await session.execute(
        select(func.count(), func.coalesce(func.sum(Order.price), 0)).where(Order.created_at >= today_start)
    )
    row = r.one()
    return int(row[0]), int(row[1])

# ── File utils ────────────────────────────────────────────────────────────────
async def save_export_file(lines, prefix):
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fp = os.path.join(EXPORTS_DIR, f"{prefix}_{ts}.txt")
    async with aiofiles.open(fp, "w", encoding="utf-8") as f:
        await f.write("\n".join(lines))
    return fp

async def save_order_file(accounts_data, order_id):
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"order_{order_id}_{ts}.txt"
    fp = os.path.join(EXPORTS_DIR, filename)
    async with aiofiles.open(fp, "w", encoding="utf-8") as f:
        await f.write("\n".join(f"{u}|{p}" for u, p in accounts_data))
    return fp, filename

async def save_bill_image(file_bytes, extension="jpg"):
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    fp = os.path.join(UPLOADS_DIR, f"bill_{uuid.uuid4().hex}.{extension}")
    async with aiofiles.open(fp, "wb") as f:
        await f.write(file_bytes)
    return fp

async def save_qr_image(file_bytes):
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    async with aiofiles.open(QR_IMAGE_PATH, "wb") as f:
        await f.write(file_bytes)
    return QR_IMAGE_PATH

def qr_exists():
    return os.path.isfile(QR_IMAGE_PATH)

# ── Keyboards ─────────────────────────────────────────────────────────────────
def main_menu_kb():
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="🛒 Mua Acc"), KeyboardButton(text="💳 Nạp Tiền"))
    b.row(KeyboardButton(text="👤 Tài Khoản"), KeyboardButton(text="📦 Đơn Hàng"))
    b.row(KeyboardButton(text="🎁 Giftcode"), KeyboardButton(text="📅 Điểm Danh"))
    b.row(KeyboardButton(text="🔗 Giới Thiệu"), KeyboardButton(text="❓ FAQ"))
    b.row(KeyboardButton(text="☎ Hỗ Trợ"), KeyboardButton(text="🏠 Trang Chủ"))
    b.row(KeyboardButton(text="🟢 Bot Đang Chạy 24/7"))
    return b.as_markup(resize_keyboard=True)

def cancel_kb():
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="❌ Hủy"))
    return b.as_markup(resize_keyboard=True)

def back_home_inline_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 Quay Lại Trang Chủ", callback_data="go_home"))
    return b.as_markup()

def deposit_approval_kb(deposit_id):
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ DUYỆT", callback_data=f"approve_deposit:{deposit_id}"),
        InlineKeyboardButton(text="❌ TỪ CHỐI", callback_data=f"reject_deposit:{deposit_id}"),
    )
    return b.as_markup()

def admin_menu_kb():
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="📊 Dashboard"), KeyboardButton(text="🏆 Top Nạp/Mua"))
    b.row(KeyboardButton(text="📥 Import TXT"), KeyboardButton(text="📦 Xem Kho"))
    b.row(KeyboardButton(text="📊 Thống Kê"), KeyboardButton(text="🎫 Tạo Giftcode"))
    b.row(KeyboardButton(text="💰 Cộng Tiền"), KeyboardButton(text="💸 Trừ Tiền"))
    b.row(KeyboardButton(text="📷 Đổi QR"), KeyboardButton(text="📥 Bill Chờ"))
    b.row(KeyboardButton(text="📢 Broadcast"), KeyboardButton(text="📣 Đặt Banner"))
    b.row(KeyboardButton(text="🚫 Ban User"), KeyboardButton(text="✅ Unban User"))
    b.row(KeyboardButton(text="🗑 Xóa Account"), KeyboardButton(text="🧹 Dọn Acc Rác"))
    b.row(KeyboardButton(text="📤 Export Chưa Bán"), KeyboardButton(text="📤 Export Đã Bán"))
    b.row(KeyboardButton(text="🛠 Chế Độ Bảo Trì"))
    b.row(KeyboardButton(text="🔙 Menu Chính"), KeyboardButton(text="🟢 Bot Đang Chạy 24/7"))
    return b.as_markup(resize_keyboard=True)

# ── Middleware ────────────────────────────────────────────────────────────────
class AuthMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user is None: return await handler(event, data)
        is_admin = user.id in ADMIN_IDS
        fullname = (user.full_name or "").strip() or user.username or str(user.id)

        referred_by = None
        if isinstance(event, Message) and (event.text or "").startswith("/start "):
            payload = event.text.split(maxsplit=1)[1].strip()
            if payload.lstrip("-").isdigit():
                referred_by = int(payload)

        async with AsyncSessionLocal() as session:
            db_user = await get_or_create_user(session, user.id, user.username, fullname, is_admin, referred_by=referred_by)
            if db_user.is_admin != is_admin:
                db_user.is_admin = is_admin
                await session.commit()
            data["db_user"] = db_user
            data["db_session"] = session
            data["is_admin"] = is_admin
            if db_user.is_banned and not is_admin:
                if isinstance(event, Message): await event.answer("🚫 Bạn đã bị cấm sử dụng bot.")
                return
            # ── Chế độ bảo trì: chỉ chặn thao tác của user thường, Admin vẫn dùng bình thường ──
            if not is_admin and await is_maintenance_mode(session):
                allowed_texts = {"☎ Hỗ Trợ", "🏠 Trang Chủ", "🟢 Bot Đang Chạy 24/7"}
                text = getattr(event, "text", None)
                is_start_cmd = isinstance(event, Message) and (event.text or "").startswith("/start")
                if not (is_start_cmd or text in allowed_texts):
                    if isinstance(event, Message):
                        await event.answer("🛠 <b>Bot đang bảo trì!</b>\nVui lòng quay lại sau ít phút. Xin lỗi vì sự bất tiện này.", parse_mode="HTML")
                    elif isinstance(event, CallbackQuery):
                        await event.answer("🛠 Bot đang bảo trì, vui lòng quay lại sau!", show_alert=True)
                    return
            return await handler(event, data)

# ── States ────────────────────────────────────────────────────────────────────
class ShopState(StatesGroup):
    waiting_quantity = State()

class DepositState(StatesGroup):
    waiting_amount = State()
    waiting_bill = State()

class GiftState(StatesGroup):
    waiting_code = State()

class AdminStates(StatesGroup):
    waiting_qr = State()
    waiting_import_file = State()
    waiting_add_balance_id = State()
    waiting_add_balance_amount = State()
    waiting_subtract_balance_id = State()
    waiting_subtract_balance_amount = State()
    waiting_ban_id = State()
    waiting_unban_id = State()
    waiting_delete_username = State()
    waiting_broadcast_text = State()
    waiting_giftcode_amount = State()
    waiting_giftcode_uses = State()
    waiting_banner_text = State()

def admin_only(func):
    @functools.wraps(func)
    async def wrapper(message: Message, is_admin: bool, *args, **kwargs):
        if not is_admin:
            await message.answer("❌ Bạn không có quyền truy cập.")
            return
        return await func(message, is_admin=is_admin, *args, **kwargs)
    return wrapper

# ── Router ────────────────────────────────────────────────────────────────────
router = Router()

# ── Xử lý nút Bot Đang Chạy ───────────────────────────────────────────────────
@router.message(lambda m: m.text == "🟢 Bot Đang Chạy 24/7")
async def bot_status_click(message: Message):
    await message.answer("⚡ <b>Hệ thống trực tuyến!</b>\nBot vẫn đang vận hành ổn định, xanh chín 24/7 trên máy chủ Render.", parse_mode="HTML")

# ── /start & home ─────────────────────────────────────────────────────────────
async def _home_text(db_user: User, db_session) -> str:
    available = await get_available_count(db_session)
    name = db_user.fullname
    banner = await get_setting(db_session, "banner_text", "")
    banner_block = f"📣 <b>Thông báo:</b> {banner}\n\n━━━━━━━━━━━━━━━━━━\n" if banner else ""
    return (
        f"{banner_block}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🛒 <b>SHOP GARENA PREMIUM</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Xin chào <b>{name}</b>!\n"
        f"💰 Số dư: <b>{db_user.balance:,} VNĐ</b>\n"
        f"📦 Kho còn: <b>{available:,} acc</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👇 Chọn một chức năng bên dưới:"
    )

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, db_user: User, db_session, bot: Bot):
    await state.clear()
    await message.answer(await _home_text(db_user, db_session), parse_mode="HTML", reply_markup=main_menu_kb())

@router.message(lambda m: m.text == "🏠 Trang Chủ")
async def home(message: Message, state: FSMContext, db_user: User, db_session):
    await state.clear()
    await message.answer(await _home_text(db_user, db_session), parse_mode="HTML", reply_markup=main_menu_kb())

@router.callback_query(F.data == "go_home")
async def cb_go_home(callback: CallbackQuery, state: FSMContext, db_user: User, db_session):
    await state.clear()
    await callback.message.answer(await _home_text(db_user, db_session), parse_mode="HTML", reply_markup=main_menu_kb())
    await callback.answer()

# ── Điểm Danh Hằng Ngày ───────────────────────────────────────────────────────
@router.message(lambda m: m.text == "📅 Điểm Danh")
async def daily_checkin(message: Message, state: FSMContext, db_user: User, db_session):
    await state.clear()
    ok, reward, streak = await do_daily_checkin(db_session, db_user)
    if not ok:
        await message.answer(
            f"📅 <b>Điểm Danh Hằng Ngày</b>\n\n"
            f"✅ Bạn đã điểm danh hôm nay rồi, hẹn gặp lại vào ngày mai!\n"
            f"🔥 Chuỗi điểm danh hiện tại: <b>{db_user.checkin_streak} ngày</b>\n"
            f"⭐ Tổng điểm: <b>{db_user.points:,} điểm</b>",
            parse_mode="HTML",
        )
        return
    await message.answer(
        f"📅 <b>Điểm Danh Thành Công!</b>\n\n"
        f"🎁 Nhận được: <b>+{reward:,} điểm</b>\n"
        f"🔥 Chuỗi điểm danh: <b>{streak} ngày</b>\n"
        f"⭐ Tổng điểm hiện có: <b>{db_user.points:,} điểm</b>\n\n"
        f"💡 Điểm danh liên tục để nhận thêm điểm thưởng streak!",
        parse_mode="HTML",
    )

# ── Giftcode ──────────────────────────────────────────────────────────────────
@router.message(lambda m: m.text == "🎁 Giftcode")
async def giftcode_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🎁 <b>Nhập Mã Giftcode</b>\n\n"
        "Vui lòng nhập mã giftcode bạn có để nhận thưởng vào số dư.\n"
        "Bấm ❌ Hủy để quay lại.",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await state.set_state(GiftState.waiting_code)

@router.message(GiftState.waiting_code, lambda m: m.text == "❌ Hủy")
async def giftcode_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Đã hủy nhập giftcode.", reply_markup=main_menu_kb())

@router.message(GiftState.waiting_code)
async def giftcode_submit(message: Message, state: FSMContext, db_user: User, db_session):
    code = (message.text or "").strip()
    await state.clear()
    status, amount = await redeem_giftcode(db_session, code, db_user)
    if status == "ok":
        await message.answer(
            f"✅ <b>Nhập Giftcode Thành Công!</b>\n\n"
            f"💵 Nhận được: <b>+{amount:,} VNĐ</b>\n"
            f"💰 Số dư mới: <b>{db_user.balance:,} VNĐ</b>",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
    elif status == "already_used":
        await message.answer("⚠️ Bạn đã sử dụng mã giftcode này trước đó rồi.", reply_markup=main_menu_kb())
    elif status == "exhausted":
        await message.answer("⚠️ Mã giftcode này đã hết lượt sử dụng.", reply_markup=main_menu_kb())
    else:
        await message.answer("❌ Mã giftcode không tồn tại hoặc không hợp lệ.", reply_markup=main_menu_kb())

# ── Giới Thiệu Bạn Bè ─────────────────────────────────────────────────────────
@router.message(lambda m: m.text == "🔗 Giới Thiệu")
async def referral_page(message: Message, state: FSMContext, db_user: User, db_session, bot: Bot):
    await state.clear()
    bot_username = BOT_USERNAME or (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={db_user.telegram_id}"
    stats = await get_referral_stats(db_session, db_user.telegram_id)
    await message.answer(
        f"🔗 <b>Giới Thiệu Bạn Bè — Nhận Thưởng</b>\n\n"
        f"🔗 Link giới thiệu của bạn:\n<code>{link}</code>\n\n"
        f"🎁 Khi bạn bè nạp tiền lần đầu (≥ {REFERRAL_MIN_DEPOSIT:,} VNĐ), bạn nhận <b>{REFERRAL_REWARD:,} VNĐ</b>.\n\n"
        f"📊 <b>Thống kê giới thiệu:</b>\n"
        f"👥 Đã mời: <b>{stats['total_invited']}</b> người\n"
        f"✅ Đã nạp & nhận thưởng: <b>{stats['rewarded']}</b> người\n"
        f"💰 Tổng thưởng đã nhận: <b>{stats['total_earned']:,} VNĐ</b>",
        parse_mode="HTML",
    )

# ── FAQ / Hướng Dẫn Sử Dụng ───────────────────────────────────────────────────
@router.message(lambda m: m.text == "❓ FAQ")
async def faq_page(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❓ <b>FAQ — Câu Hỏi Thường Gặp</b>\n\n"
        "🛒 <b>Mua acc như thế nào?</b>\n"
        "Bấm <b>Mua Acc</b> → nhập số lượng → hệ thống tự động random và gửi acc ngay.\n\n"
        "💳 <b>Nạp tiền như thế nào?</b>\n"
        "Bấm <b>Nạp Tiền</b> → nhập số tiền → chuyển khoản theo mã QR → gửi ảnh hóa đơn → chờ Admin duyệt.\n\n"
        "🎁 <b>Giftcode dùng để làm gì?</b>\n"
        "Nhập mã giftcode để cộng thẳng tiền vào số dư tài khoản.\n\n"
        "🔗 <b>Giới thiệu bạn bè có lợi gì?</b>\n"
        "Mời bạn bè dùng link riêng, khi họ nạp tiền lần đầu bạn sẽ được thưởng.\n\n"
        "☎️ Cần hỗ trợ thêm? Bấm <b>Hỗ Trợ</b> để liên hệ Admin.",
        parse_mode="HTML",
    )

@router.message(lambda m: m.text == "☎ Hỗ Trợ")
async def support(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "☎ <b>Hỗ Trợ Khách Hàng</b>\n\n"
        "Nếu gặp lỗi hoặc cần giải đáp, liên hệ Admin:\n"
        "👤 Admin: @lananh9719\n\n"
        "⏰ Hoạt động: 8:00 - 22:00 hàng ngày.",
        parse_mode="HTML",
    )

# ── Shop Liên Quân ────────────────────────────────────────────────────────────
@router.message(lambda m: m.text == "🛒 Mua Acc")
async def buy_acc_start(message: Message, state: FSMContext, db_session):
    await state.clear()
    available = await get_available_count(db_session)
    await message.answer(
        f"🛒 <b>Mua Acc Liên Quân</b>\n\n"
        f"💵 Giá bán: <b>{ACCOUNT_PRICE:,} VNĐ / acc</b>\n"
        f"📦 Kho còn: <b>{available:,} acc</b>\n"
        f"⚠️ Yêu cầu mua tối thiểu: <b>{MIN_ORDER_QTY} acc</b>\n\n"
        "Vui lòng nhập số lượng acc muốn mua:",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await state.set_state(ShopState.waiting_quantity)

@router.message(ShopState.waiting_quantity, F.text == "❌ Hủy")
async def buy_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Đã hủy giao dịch.", reply_markup=main_menu_kb())

@router.message(ShopState.waiting_quantity, ~F.text.in_(MENU_BUTTONS))
async def buy_acc_quantity(message: Message, state: FSMContext, db_user: User, db_session):
    text = message.text or ""
    if not text.isdigit():
        await message.answer("⚠️ Vui lòng nhập số nguyên hợp lệ.")
        return
    quantity = int(text)
    if quantity < MIN_ORDER_QTY:
        await message.answer(f"⚠️ Số lượng tối thiểu là <b>{MIN_ORDER_QTY} acc</b>.", parse_mode="HTML")
        return
    total_price = quantity * ACCOUNT_PRICE

    r_u = await db_session.execute(select(User).where(User.id == db_user.id).with_for_update())
    fresh_user = r_u.scalar_one_or_none()

    if fresh_user.balance < total_price:
        shortage = total_price - fresh_user.balance
        await message.answer(
            f"❌ <b>Số dư VNĐ không đủ!</b>\n\n"
            f"💰 Hiện có: <b>{fresh_user.balance:,} VNĐ</b>\n"
            f"💵 Cần thanh toán: <b>{total_price:,} VNĐ</b>\n"
            f"⚠️ Thiếu: <b>{shortage:,} VNĐ</b>\n\nVui lòng nạp thêm tiền.",
            parse_mode="HTML", reply_markup=main_menu_kb()
        )
        await state.clear()
        return

    available = await get_available_count(db_session)
    if available < quantity:
        await message.answer(f"❌ Kho không đủ hàng!\n📦 Kho hiện còn: <b>{available:,} acc</b>", parse_mode="HTML", reply_markup=main_menu_kb())
        await state.clear()
        return

    accounts = await pick_random_accounts(db_session, quantity)
    if len(accounts) < quantity:
        await message.answer("❌ Có lỗi xảy ra khi lấy tài khoản. Thử lại sau.", reply_markup=main_menu_kb())
        await state.clear()
        return

    order = await create_order(db_session, fresh_user.id, quantity, total_price, "")
    fresh_user.balance -= total_price
    fresh_user.points += (total_price // 1000) * POINTS_PER_VND_SPENT
    await mark_accounts_sold(db_session, accounts, order.id)

    try:
        account_data = [(a.username, a.password) for a in accounts]
        filepath, filename = await save_order_file(account_data, order.id)
        order.file_name = filename
        await db_session.commit()
    except Exception:
        # ── Hoàn tiền tự động nếu lưu/giao dịch lỗi ──
        logger.exception("Lỗi khi tạo file đơn hàng #%s, tiến hành hoàn tiền tự động", order.id)
        await db_session.rollback()
        order2 = await create_order(db_session, fresh_user.id, 0, 0, "REFUND_FAILED_ORDER")
        order2.status = OrderStatus.cancelled
        fresh_user.balance += total_price
        for a in accounts:
            a.status = AccountStatus.available
            a.order_id = None
        await db_session.commit()
        await state.clear()
        await message.answer(
            "❌ <b>Có lỗi xảy ra khi xử lý đơn hàng!</b>\n\n💵 Hệ thống đã tự động hoàn tiền vào số dư của bạn.",
            parse_mode="HTML", reply_markup=main_menu_kb()
        )
        return

    await state.clear()

    await message.answer(
        f"✅ <b>Mua hàng thành công!</b>\n\n"
        f"📦 Số lượng: <b>{quantity} acc</b>\n"
        f"💵 Tổng tiền: <b>{total_price:,} VNĐ</b>\n"
        f"🧾 Mã đơn: <b>#{order.id}</b>\n\nĐang gửi file...",
        parse_mode="HTML", reply_markup=main_menu_kb()
    )
    await message.answer_document(FSInputFile(filepath, filename=filename), caption=f"📄 Đơn hàng #{order.id} — {quantity} acc")
    await message.answer(f"📌 Link check acc free:\n{CHECKER_LINK}")

# ── Tài khoản & Đơn hàng ─────────────────────────────────────────────────────
@router.message(lambda m: m.text == "👤 Tài Khoản")
async def my_account(message: Message, state: FSMContext, db_user: User, db_session):
    await state.clear()
    joined = db_user.created_at.strftime("%d/%m/%Y") if db_user.created_at else "N/A"
    orders = await get_user_orders(db_session, db_user.id, limit=9999)
    uname = f"@{db_user.username}" if db_user.username else "Không có"
    total_spent = await get_user_total_spent(db_session, db_user.id)
    total_deposited = await get_user_total_deposited(db_session, db_user.id)
    tier = get_membership_tier(total_spent)
    await message.answer(
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>HỒ SƠ CỦA TÔI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID Telegram: <code>{db_user.telegram_id}</code>\n"
        f"👤 Username: {uname}\n"
        f"📛 Tên: {db_user.fullname}\n"
        f"📅 Tham gia ngày: {joined}\n"
        f"{tier} Hạng thành viên\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Số dư: <b>{db_user.balance:,} VNĐ</b>\n"
        f"💳 Tổng đã nạp: <b>{total_deposited:,} VNĐ</b>\n"
        f"🛒 Tổng đã mua: <b>{total_spent:,} VNĐ</b>\n"
        f"📦 Số đơn: <b>{len(orders)}</b>\n"
        f"⭐ Điểm thưởng: <b>{db_user.points:,} điểm</b>\n"
        f"🔥 Chuỗi điểm danh: <b>{db_user.checkin_streak} ngày</b>\n"
        f"━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

@router.message(lambda m: m.text == "📦 Đơn Hàng")
async def my_orders(message: Message, state: FSMContext, db_user: User, db_session):
    await state.clear()
    orders = await get_user_orders(db_session, db_user.id, limit=20)
    if not orders:
        await message.answer("📦 Bạn chưa mua đơn hàng nào.")
        return
    lines = ["📦 <b>20 Đơn Hàng Gần Nhất</b>\n"]
    for i, o in enumerate(orders, 1):
        created = o.created_at.strftime("%d/%m/%Y %H:%M") if o.created_at else "N/A"
        lines.append(f"{i}. Đơn #{o.id} — {o.quantity} acc — {o.price:,} VNĐ — {created}")
    await message.answer("\n".join(lines), parse_mode="HTML")

# ── Nạp tiền VNĐ ──────────────────────────────────────────────────────────────
def sepay_enabled() -> bool:
    return bool(SEPAY_API_KEY and SEPAY_BANK_ACCOUNT)

@router.message(lambda m: m.text == "💳 Nạp Tiền")
async def deposit_start(message: Message, state: FSMContext):
    await state.clear()
    if not sepay_enabled() and not qr_exists():
        await message.answer("⚠️ Hệ thống nạp tiền đang bảo trì (Thiếu QR). Vui lòng liên hệ Admin.")
        return
    await message.answer("💳 <b>Nạp Tiền</b>\n\nNhập số tiền muốn nạp (tối thiểu 10,000VNĐ):", parse_mode="HTML", reply_markup=cancel_kb())
    await state.set_state(DepositState.waiting_amount)

@router.message(DepositState.waiting_amount, F.text == "❌ Hủy")
async def deposit_cancel_amount(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Đã hủy nạp tiền.", reply_markup=main_menu_kb())

@router.message(DepositState.waiting_amount, ~F.text.in_(MENU_BUTTONS))
async def deposit_amount(message: Message, state: FSMContext, db_user: User, db_session):
    text = (message.text or "").replace(",", "").replace(".", "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Vui lòng nhập số tiền hợp lệ.")
        return
    amount = int(text)

    if sepay_enabled():
        # ── Luồng thanh toán TỰ ĐỘNG qua SePay: tạo yêu cầu nạp trước để có mã nội dung CK ──
        deposit = await create_deposit(db_session, db_user.id, amount)
        qr_url = build_vietqr_url(amount, deposit.code)
        await state.update_data(deposit_id=deposit.id, amount=amount)
        await message.answer_photo(
            qr_url,
            caption=(
                f"💳 <b>Quét QR Để Nạp Tiền Tự Động</b>\n\n"
                f"💵 Số tiền: <b>{amount:,} VNĐ</b>\n"
                f"📝 Nội dung CK (bắt buộc đúng): <code>{deposit.code}</code>\n"
                f"⏰ Hiệu lực: <b>{DEPOSIT_EXPIRE_MINUTES} phút</b>\n\n"
                f"⚡️ Hệ thống sẽ <b>tự động cộng tiền trong vài giây</b> sau khi bạn chuyển khoản đúng nội dung — "
                f"không cần gửi bill hay chờ Admin duyệt.\n\n"
                f"⚠️ Nếu chuyển sai nội dung, vui lòng gửi ảnh bill tại đây để Admin đối soát thủ công."
            ),
            parse_mode="HTML", reply_markup=main_menu_kb()
        )
        await state.set_state(DepositState.waiting_bill)
        return

    # ── Luồng THỦ CÔNG (khi chưa cấu hình SePay): giữ nguyên như bản cũ ──
    await state.update_data(amount=amount)
    await message.answer_photo(
        FSInputFile(QR_IMAGE_PATH),
        caption=f"💵 Số tiền nạp: <b>{amount:,} VNĐ</b>\n\n📷 Vui lòng gửi ảnh chụp màn hình bill chuyển khoản:",
        parse_mode="HTML", reply_markup=cancel_kb()
    )
    await state.set_state(DepositState.waiting_bill)

@router.message(DepositState.waiting_bill, F.text == "❌ Hủy")
async def deposit_cancel_bill(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Đã hủy nạp tiền.", reply_markup=main_menu_kb())

@router.message(DepositState.waiting_bill, F.photo)
async def deposit_bill_photo(message: Message, state: FSMContext, bot: Bot, db_user: User, db_session):
    data = await state.get_data()
    amount = data.get("amount", 0)
    existing_deposit_id = data.get("deposit_id")
    await state.clear()
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    bill_path = await save_bill_image(file_bytes.read(), "jpg")

    if existing_deposit_id:
        # Yêu cầu nạp tự động đã tồn tại (từ luồng SePay) — chỉ đính kèm ảnh bill để Admin đối soát nếu cần
        deposit = await get_deposit_by_id(db_session, existing_deposit_id)
        if deposit is None or deposit.status != DepositStatus.pending:
            await message.answer("✅ Giao dịch của bạn đã được xử lý (có thể đã tự động cộng tiền trước đó).", reply_markup=main_menu_kb())
            return
        deposit.bill_image = bill_path
        await db_session.commit()
    else:
        deposit = await create_deposit(db_session, db_user.id, amount, bill_path)

    uname = f"@{db_user.username}" if db_user.username else "Không có"
    now_str = datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S")
    caption = (
        f"💳 <b>YÊU CẦU NẠP TIỀN (cần đối soát thủ công)</b>\n\n"
        f"🆔 ID Telegram: <code>{db_user.telegram_id}</code>\n"
        f"👤 Username: {uname}\n"
        f"📛 Tên: {db_user.fullname}\n"
        f"💵 Số tiền: <b>{deposit.amount:,} VNĐ</b>\n"
        f"🕐 Thời gian: {now_str}\n"
        f"🧾 Mã Bill nạp: #{deposit.id}"
        + (f" — Nội dung CK: <code>{deposit.code}</code>" if deposit.code else "")
    )
    kb = deposit_approval_kb(deposit.id)
    for admin_id in ADMIN_IDS:
        try:
            await message.forward(admin_id)
            await bot.send_message(admin_id, caption, parse_mode="HTML", reply_markup=kb)
        except Exception: pass
    await message.answer("✅ <b>Đã gửi bill cho Admin!</b>\n\n Vui lòng đợi trong giây lát hệ thống đang duyệt.", parse_mode="HTML", reply_markup=main_menu_kb())

@router.message(DepositState.waiting_bill, ~F.text.in_(MENU_BUTTONS))
async def deposit_bill_invalid(message: Message):
    await message.answer("⚠️ Vui lòng gửi hình ảnh hóa đơn giao dịch.")

@router.callback_query(F.data.startswith("approve_deposit:"))
async def cb_approve_deposit(callback: CallbackQuery, bot: Bot, is_admin: bool, db_session):
    if not is_admin: await callback.answer("❌ Bạn không có quyền.", show_alert=True); return
    deposit_id = int(callback.data.split(":")[1])
    deposit = await approve_deposit(db_session, deposit_id, callback.from_user.id)
    if deposit is None: await callback.answer("⚠️ Bill không tồn tại hoặc đã xử lý trước đó.", show_alert=True); return
    user_after = await add_balance(db_session, deposit.user_id, deposit.amount)
    user_tg_id = deposit.user.telegram_id if deposit.user else None
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(f"✅ Đã duyệt nạp tiền thành công <b>{deposit.amount:,} VNĐ</b> cho đơn #{deposit_id}", parse_mode="HTML")
    if user_tg_id:
        try: await bot.send_message(user_tg_id, f"✅ <b>Nạp tiền thành công!</b>\n\n💵 Cộng: <b>{deposit.amount:,} VNĐ</b>\n💰 Số dư ví VNĐ: <b>{user_after.balance:,} VNĐ</b>", parse_mode="HTML")
        except Exception: pass
    if user_after is not None:
        await maybe_reward_referrer(db_session, bot, user_after, deposit.amount)
    await callback.answer("✅ Hoàn tất!")

@router.callback_query(F.data.startswith("reject_deposit:"))
async def cb_reject_deposit(callback: CallbackQuery, bot: Bot, is_admin: bool, db_session):
    if not is_admin: await callback.answer("❌ Bạn không có quyền.", show_alert=True); return
    deposit_id = int(callback.data.split(":")[1])
    deposit = await reject_deposit(db_session, deposit_id, callback.from_user.id)
    if deposit is None: await callback.answer("⚠️ Bill không tồn tại hoặc đã xử lý.", show_alert=True); return
    user_tg_id = deposit.user.telegram_id if deposit.user else None
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(f"❌ Đã từ chối đơn nạp #{deposit_id}", parse_mode="HTML")
    if user_tg_id:
        try: await bot.send_message(user_tg_id, f"❌ <b>Đơn nạp tiền bị từ chối!</b>\n\n💵 Số tiền: <b>{deposit.amount:,} VNĐ</b>\nVui lòng kiểm tra lại hình ảnh hóa đơn.", parse_mode="HTML")
        except Exception: pass
    await callback.answer("❌ Đã từ chối!")

# ── Admin Panel ───────────────────────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message, is_admin: bool):
    if not is_admin: await message.answer("❌ Bạn không có quyền."); return
    await message.answer("🔐 <b>HỆ THỐNG ĐIỀU HÀNH ADMIN</b>", parse_mode="HTML", reply_markup=admin_menu_kb())

@router.message(lambda m: m.text == "🔙 Menu Chính")
async def back_to_main(message: Message):
    await message.answer("🏠 Quay về Menu chính", reply_markup=main_menu_kb())

@router.message(lambda m: m.text == "📊 Dashboard")
@admin_only
async def admin_dashboard(message: Message, is_admin: bool, db_session):
    t_acc = await get_total_count(db_session)
    a_acc = await get_available_count(db_session)
    s_acc = await get_sold_count(db_session)
    orders = await get_all_orders(db_session, 9999)
    users = await get_all_users(db_session)
    bills = await get_pending_deposits(db_session)
    orders_today, revenue_today = await get_orders_today_count_and_revenue(db_session)
    maintenance = await is_maintenance_mode(db_session)
    await message.answer(
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>DASHBOARD HỆ THỐNG</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 Tổng người dùng: <b>{len(users)}</b>\n"
        f"📦 Tổng acc trong kho: <b>{t_acc}</b>\n"
        f"✅ Acc chưa bán: <b>{a_acc}</b>\n"
        f"🔴 Acc đã bán: <b>{s_acc}</b>\n"
        f"🧾 Tổng số đơn: <b>{len(orders)}</b>\n"
        f"📅 Đơn hôm nay: <b>{orders_today}</b> — Doanh thu: <b>{revenue_today:,} VNĐ</b>\n"
        f"💰 Tổng doanh thu: <b>{sum(o.price for o in orders):,} VNĐ</b>\n"
        f"⏳ Hoá đơn chờ duyệt: <b>{len(bills)}</b>\n"
        f"🛠 Chế độ bảo trì: <b>{'BẬT ⚠️' if maintenance else 'TẮT ✅'}</b>\n"
        f"━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML"
    )

@router.message(lambda m: m.text == "🏆 Top Nạp/Mua")
@admin_only
async def admin_top_stats(message: Message, is_admin: bool, db_session):
    top_dep = await get_top_depositors(db_session, 5)
    top_buy = await get_top_buyers(db_session, 5)
    lines = ["🏆 <b>TOP NẠP TIỀN</b>\n"]
    if not top_dep:
        lines.append("Chưa có dữ liệu.")
    for i, (u, total) in enumerate(top_dep, 1):
        lines.append(f"{i}. {u.fullname} — <b>{int(total):,} VNĐ</b>")
    lines.append("\n🏆 <b>TOP MUA HÀNG</b>\n")
    if not top_buy:
        lines.append("Chưa có dữ liệu.")
    for i, (u, total) in enumerate(top_buy, 1):
        lines.append(f"{i}. {u.fullname} — <b>{int(total):,} VNĐ</b>")
    await message.answer("\n".join(lines), parse_mode="HTML")

# ── Giftcode (Admin) ──────────────────────────────────────────────────────────
@router.message(lambda m: m.text == "🎫 Tạo Giftcode")
@admin_only
async def admin_giftcode_start(message: Message, state: FSMContext, is_admin: bool):
    await message.answer("🎫 Nhập số tiền VNĐ mỗi giftcode sẽ cộng cho người dùng:", reply_markup=cancel_kb())
    await state.set_state(AdminStates.waiting_giftcode_amount)

@router.message(AdminStates.waiting_giftcode_amount, lambda m: m.text == "❌ Hủy")
async def admin_giftcode_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Đã hủy.", reply_markup=admin_menu_kb())

@router.message(AdminStates.waiting_giftcode_amount)
async def admin_giftcode_amount(message: Message, state: FSMContext):
    t = (message.text or "").replace(",", "").strip()
    if not t.isdigit() or int(t) <= 0:
        await message.answer("⚠️ Số tiền không hợp lệ."); return
    await state.update_data(gc_amount=int(t))
    await message.answer("🔢 Nhập số lượt sử dụng tối đa (vd: 1 = chỉ 1 người dùng được):")
    await state.set_state(AdminStates.waiting_giftcode_uses)

@router.message(AdminStates.waiting_giftcode_uses)
async def admin_giftcode_uses(message: Message, state: FSMContext, db_session):
    t = (message.text or "").strip()
    if not t.isdigit() or int(t) <= 0:
        await message.answer("⚠️ Số lượt không hợp lệ."); return
    data = await state.get_data(); amount = data["gc_amount"]; await state.clear()
    gc = await create_giftcode(db_session, amount, max_uses=int(t))
    await message.answer(
        f"✅ <b>Đã tạo Giftcode!</b>\n\n"
        f"🎁 Mã: <code>{gc.code}</code>\n"
        f"💵 Giá trị: <b>{amount:,} VNĐ</b>\n"
        f"🔢 Số lượt: <b>{gc.max_uses}</b>",
        parse_mode="HTML", reply_markup=admin_menu_kb()
    )

# ── Banner Thông Báo (Admin) ──────────────────────────────────────────────────
@router.message(lambda m: m.text == "📣 Đặt Banner")
@admin_only
async def admin_banner_start(message: Message, state: FSMContext, is_admin: bool):
    await message.answer(
        "📣 Nhập nội dung banner hiển thị ở Trang Chủ (gửi <code>xóa</code> để gỡ banner):",
        parse_mode="HTML", reply_markup=cancel_kb()
    )
    await state.set_state(AdminStates.waiting_banner_text)

@router.message(AdminStates.waiting_banner_text, lambda m: m.text == "❌ Hủy")
async def admin_banner_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Đã hủy.", reply_markup=admin_menu_kb())

@router.message(AdminStates.waiting_banner_text)
async def admin_banner_set(message: Message, state: FSMContext, db_session):
    text = (message.text or "").strip()
    await state.clear()
    if text.lower() == "xóa":
        await set_setting(db_session, "banner_text", "")
        await message.answer("✅ Đã gỡ banner thông báo.", reply_markup=admin_menu_kb())
        return
    await set_setting(db_session, "banner_text", text)
    await message.answer(f"✅ Đã cập nhật banner:\n\n📣 {text}", reply_markup=admin_menu_kb())

# ── Chế Độ Bảo Trì (Admin) ────────────────────────────────────────────────────
@router.message(lambda m: m.text == "🛠 Chế Độ Bảo Trì")
@admin_only
async def admin_toggle_maintenance(message: Message, is_admin: bool, db_session):
    current = await is_maintenance_mode(db_session)
    new_value = "0" if current else "1"
    await set_setting(db_session, "maintenance_mode", new_value)
    status = "🛠 ĐÃ BẬT — người dùng thường sẽ không thao tác được." if new_value == "1" else "✅ ĐÃ TẮT — bot hoạt động bình thường."
    await message.answer(f"🛠 <b>Chế Độ Bảo Trì</b>\n\n{status}", parse_mode="HTML")

@router.message(lambda m: m.text == "📦 Xem Kho")
@admin_only
async def admin_view_stock(message: Message, is_admin: bool, db_session):
    t = await get_total_count(db_session)
    a = await get_available_count(db_session)
    s = await get_sold_count(db_session)
    await message.answer(f"📦 <b>Trạng Thái Kho</b>\n\n📊 Tổng: <b>{t}</b>\n✅ Chưa bán: <b>{a}</b>\n🔴 Đã bán: <b>{s}</b>", parse_mode="HTML")

@router.message(lambda m: m.text == "📊 Thống Kê")
@admin_only
async def admin_stats(message: Message, is_admin: bool, db_session):
    orders = await get_all_orders(db_session, 9999)
    users = await get_all_users(db_session)
    t = await get_total_count(db_session)
    a = await get_available_count(db_session)
    s = await get_sold_count(db_session)
    await message.answer(
        f"📊 <b>Thống Kê Vận Hành</b>\n\n👥 Tổng User: <b>{len(users)}</b>\n📦 Tổng Acc: <b>{t}</b>\n✅ Còn: <b>{a}</b>\n🔴 Đã bán: <b>{s}</b>\n🧾 Tổng đơn: <b>{len(orders)}</b>\n💰 Tổng doanh thu: <b>{sum(o.price for o in orders):,} VNĐ</b>",
        parse_mode="HTML"
    )

@router.message(lambda m: m.text == "📥 Import TXT")
@admin_only
async def admin_import_start(message: Message, state: FSMContext, is_admin: bool):
    await message.answer(
        "📥 Vui lòng gửi file <code>.TXT</code> chứa tài khoản.\n\n"
        "✅ Hỗ trợ <b>format checker</b> (khuyên dùng):\n"
        "<code>username:password|UID=...|Skin=X|Tướng=Y|BAN=NO|...</code>\n\n"
        "⚠️ <b>Tự động lọc bỏ:</b>\n"
        "   🚫 Acc bị BAN\n"
        "   🗑 Acc có 0 Skin + 0 Tướng\n\n"
        "📌 Format đơn giản cũng được nhận:\n"
        "<code>username:password</code> hoặc <code>username|password</code>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_import_file)

@router.message(AdminStates.waiting_import_file, F.document)
async def admin_import_file(message: Message, state: FSMContext, bot: Bot, db_session):
    doc = message.document
    if not doc or not doc.file_name or not doc.file_name.endswith(".txt"):
        await message.answer("⚠️ File gửi lên phải có định dạng đuôi `.txt`!")
        return
    await state.clear()
    file = await bot.get_file(doc.file_id)
    raw = await bot.download_file(file.file_path)
    content = raw.read().decode("utf-8", errors="ignore")
    stats = await import_accounts(db_session, content.splitlines())
    await message.answer(
        f"📥 <b>KẾT QUẢ IMPORT KHO ACC</b>\n\n"
        f"📄 Tổng dòng: <b>{stats['total']}</b>\n"
        f"✅ Đã thêm thành công: <b>{stats['imported']}</b>\n"
        f"🔁 Bị trùng: <b>{stats['duplicates']}</b>\n"
        f"❌ Lỗi định dạng: <b>{stats['invalid']}</b>\n\n"
        f"🚫 <b>Lọc acc rác:</b>\n"
        f"   ⛔ Bị ban: <b>{stats['filtered_banned']}</b>\n"
        f"   🗑 0 skin + 0 tướng: <b>{stats['filtered_empty']}</b>",
        parse_mode="HTML"
    )

@router.message(lambda m: m.text == "💰 Cộng Tiền")
@admin_only
async def admin_add_bal_start(message: Message, state: FSMContext, is_admin: bool):
    await message.answer("💰 Nhập Telegram ID người nhận tiền VNĐ:")
    await state.set_state(AdminStates.waiting_add_balance_id)

@router.message(AdminStates.waiting_add_balance_id)
async def admin_add_bal_id(message: Message, state: FSMContext):
    t = (message.text or "").strip()
    if not t.lstrip("-").isdigit(): await message.answer("⚠️ Telegram ID phải là số."); return
    await state.update_data(target_id=int(t))
    await message.answer("💵 Nhập số tiền VNĐ cần cộng thêm:")
    await state.set_state(AdminStates.waiting_add_balance_amount)

@router.message(AdminStates.waiting_add_balance_amount)
async def admin_add_bal_amount(message: Message, state: FSMContext, db_session):
    t = (message.text or "").replace(",", "").strip()
    if not t.isdigit() or int(t) <= 0: await message.answer("⚠️ Số tiền không hợp lệ."); return
    amt = int(t); data = await state.get_data(); tid = data["target_id"]; await state.clear()
    user = await adjust_balance_by_telegram_id(db_session, tid, amt)
    if user is None: await message.answer(f"❌ Không tìm thấy User ID {tid} trong hệ thống."); return
    await message.answer(f"✅ Đã cộng <b>{amt:,} VNĐ</b> cho <b>{user.fullname}</b>\n💰 Số dư VNĐ mới: <b>{user.balance:,} VNĐ</b>", parse_mode="HTML")

@router.message(lambda m: m.text == "💸 Trừ Tiền")
@admin_only
async def admin_sub_bal_start(message: Message, state: FSMContext, is_admin: bool):
    await message.answer("💸 Nhập Telegram ID người cần trừ tiền VNĐ:")
    await state.set_state(AdminStates.waiting_subtract_balance_id)

@router.message(AdminStates.waiting_subtract_balance_id)
async def admin_sub_bal_id(message: Message, state: FSMContext):
    t = (message.text or "").strip()
    if not t.lstrip("-").isdigit(): await message.answer("⚠️ Telegram ID không hợp lệ."); return
    await state.update_data(target_id=int(t))
    await message.answer("💵 Nhập số tiền VNĐ cần trừ bớt:")
    await state.set_state(AdminStates.waiting_subtract_balance_amount)

@router.message(AdminStates.waiting_subtract_balance_amount)
async def admin_sub_bal_amount(message: Message, state: FSMContext, db_session):
    t = (message.text or "").replace(",", "").strip()
    if not t.isdigit() or int(t) <= 0: await message.answer("⚠️ Số tiền không hợp lệ."); return
    amt = int(t); data = await state.get_data(); tid = data["target_id"]; await state.clear()
    user = await adjust_balance_by_telegram_id(db_session, tid, -amt)
    if user is None: await message.answer(f"❌ Không tìm thấy User ID {tid}"); return
    await message.answer(f"✅ Đã trừ <b>{amt:,} VNĐ</b> khỏi <b>{user.fullname}</b>\n💰 Số dư VNĐ mới: <b>{user.balance:,} VNĐ</b>", parse_mode="HTML")

@router.message(lambda m: m.text == "📷 Đổi QR")
@admin_only
async def admin_change_qr_start(message: Message, state: FSMContext, is_admin: bool):
    await message.answer("📷 Vui lòng gửi ảnh mã QR nạp tiền mới lên đây:")
    await state.set_state(AdminStates.waiting_qr)

@router.message(AdminStates.waiting_qr, F.photo)
async def admin_receive_qr(message: Message, state: FSMContext, bot: Bot):
    photo = message.photo[-1]; file = await bot.get_file(photo.file_id); raw = await bot.download_file(file.file_path)
    await save_qr_image(raw.read())
    await state.clear()
    await message.answer("✅ Ảnh QR nạp tiền đã cập nhật thành công!")

@router.message(lambda m: m.text == "📥 Bill Chờ")
@admin_only
async def admin_pending_bills(message: Message, is_admin: bool, db_session):
    deposits = await get_pending_deposits(db_session)
    if not deposits: await message.answer("✅ Không có yêu cầu nạp tiền nào đang xếp hàng."); return
    lines = [f"📥 <b>Yêu Cầu Chờ Duyệt ({len(deposits)})</b>\n"]
    for d in deposits:
        uname = f"@{d.user.username}" if d.user and d.user.username else "N/A"
        name = d.user.fullname if d.user else "N/A"
        created = d.created_at.strftime("%d/%m/%Y %H:%M") if d.created_at else "N/A"
        lines.append(f"🧾 ID #{d.id} — {name} ({uname})\n   💵 {d.amount:,} VNĐ — {created}")
    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(lambda m: m.text == "📢 Broadcast")
@admin_only
async def admin_broadcast_start(message: Message, state: FSMContext, is_admin: bool):
    await message.answer("📢 Nhập nội dung tin nhắn bạn muốn gửi cho toàn bộ người chơi:")
    await state.set_state(AdminStates.waiting_broadcast_text)

@router.message(AdminStates.waiting_broadcast_text)
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot, db_session):
    text = message.text or ""; await state.clear()
    if not text: await message.answer("⚠️ Nội dung trống."); return
    users = await get_all_users(db_session)
    sent = failed = 0
    for u in users:
        if u.is_banned: continue
        try: await bot.send_message(u.telegram_id, text, parse_mode="HTML"); sent += 1
        except Exception: failed += 1
    await message.answer(f"📢 <b>Gửi Broadcast Hoàn Tất</b>\n\n✅ Thành công: <b>{sent}</b>\n❌ Thất bại: <b>{failed}</b>", parse_mode="HTML")

@router.message(lambda m: m.text == "🚫 Ban User")
@admin_only
async def admin_ban_start(message: Message, state: FSMContext, is_admin: bool):
    await message.answer("🚫 Nhập Telegram ID người cần cấm sử dụng bot:")
    await state.set_state(AdminStates.waiting_ban_id)

@router.message(AdminStates.waiting_ban_id)
async def admin_ban_execute(message: Message, state: FSMContext, db_session):
    t = (message.text or "").strip(); await state.clear()
    if not t.lstrip("-").isdigit(): await message.answer("⚠️ ID sai định dạng."); return
    ok = await ban_user(db_session, int(t))
    await message.answer(f"✅ Đã ban ID <code>{t}</code>." if ok else f"❌ Không thấy ID <code>{t}</code>", parse_mode="HTML")

@router.message(lambda m: m.text == "✅ Unban User")
@admin_only
async def admin_unban_start(message: Message, state: FSMContext, is_admin: bool):
    await message.answer("✅ Nhập Telegram ID cần mở khóa ban:")
    await state.set_state(AdminStates.waiting_unban_id)

@router.message(AdminStates.waiting_unban_id)
async def admin_unban_execute(message: Message, state: FSMContext, db_session):
    t = (message.text or "").strip(); await state.clear()
    if not t.lstrip("-").isdigit(): await message.answer("⚠️ ID sai."); return
    ok = await unban_user(db_session, int(t))
    await message.answer(f"✅ Đã gỡ ban ID <code>{t}</code>." if ok else f"❌ Không thấy ID <code>{t}</code>", parse_mode="HTML")

@router.message(lambda m: m.text == "🗑 Xóa Account")
@admin_only
async def admin_delete_acc_start(message: Message, state: FSMContext, is_admin: bool):
    await message.answer("🗑 Nhập tên tài khoản game (username) cần xoá khỏi kho:")
    await state.set_state(AdminStates.waiting_delete_username)

@router.message(AdminStates.waiting_delete_username)
async def admin_delete_acc_execute(message: Message, state: FSMContext, db_session):
    uname = (message.text or "").strip(); await state.clear()
    ok = await delete_account_by_username(db_session, uname)
    await message.answer(f"✅ Đã xóa acc <code>{uname}</code> khỏi hệ thống." if ok else f"❌ Không thấy acc có tên <code>{uname}</code>", parse_mode="HTML")

@router.message(lambda m: m.text == "🧹 Dọn Acc Rác")
@admin_only
async def admin_clean_trash(message: Message, is_admin: bool, db_session):
    trash = await get_trash_count(db_session)
    if trash == 0:
        await message.answer("✅ Kho sạch rồi, không có acc trắng nào (0 skin + 0 tướng).")
        return
    deleted = await delete_trash_accounts(db_session)
    await message.answer(
        f"🧹 <b>Dọn Kho Hoàn Tất!</b>\n\n"
        f"🗑 Đã xóa: <b>{deleted:,} acc trắng</b> (0 skin + 0 tướng)\n"
        f"✅ Kho bây giờ chỉ còn acc có skin/tướng.",
        parse_mode="HTML"
    )

@router.message(lambda m: m.text == "📤 Export Chưa Bán")
@admin_only
async def admin_export_unsold(message: Message, is_admin: bool, db_session):
    accounts = await get_unsold_accounts(db_session)
    if not accounts: await message.answer(" Kho trống rỗng."); return
    lines = [f"{a.username}|{a.password}" for a in accounts]
    fp = await save_export_file(lines, "unsold")
    await message.answer_document(FSInputFile(fp), caption=f"📤 Acc Chưa Bán\n📊 Số lượng: <b>{len(lines)}</b> acc", parse_mode="HTML")

@router.message(lambda m: m.text == "📤 Export Đã Bán")
@admin_only
async def admin_export_sold(message: Message, is_admin: bool, db_session):
    accounts = await get_sold_accounts(db_session)
    if not accounts: await message.answer(" Chưa bán được đơn nào."); return
    lines = [f"{a.username}|{a.password}" for a in accounts]
    fp = await save_export_file(lines, "sold")
    await message.answer_document(FSInputFile(fp), caption=f"📤 Acc Đã Bán\n📊 Số lượng: <b>{len(lines)}</b> acc", parse_mode="HTML")

# ── Web Server Chống Sleep + Health Check Trên Render ─────────────────────────
_last_heartbeat = {"ts": datetime.utcnow()}

async def handle_web(request):
    return web.Response(text="Bot đang vận hành ổn định 24/7!")

async def handle_health(request):
    age = (datetime.utcnow() - _last_heartbeat["ts"]).total_seconds()
    healthy = age < HEARTBEAT_INTERVAL_SEC * 3
    return web.json_response({"status": "ok" if healthy else "stale", "heartbeat_age_seconds": age}, status=200 if healthy else 503)

async def handle_app(request):
    return web.json_response({"app": "Shop Garena Premium Bot", "status": "running"})

async def handle_sepay_webhook(request):
    """Nhận webhook biến động số dư từ SePay và tự động cộng tiền khi khớp mã nạp tiền."""
    if SEPAY_API_KEY:
        auth = request.headers.get("Authorization", "")
        if auth != f"Apikey {SEPAY_API_KEY}":
            logger.warning("⚠️ Webhook SePay bị từ chối: sai API Key")
            return web.json_response({"success": False, "message": "unauthorized"}, status=401)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"success": False, "message": "invalid json"}, status=400)

    txn_id = str(payload.get("id", ""))
    transfer_type = payload.get("transferType", "in")
    amount = int(payload.get("transferAmount", 0) or 0)
    content = f"{payload.get('content') or ''} {payload.get('code') or ''}".upper()

    if transfer_type != "in" or amount <= 0 or not txn_id:
        return web.json_response({"success": True, "message": "ignored"}, status=200)

    bot: Bot = request.app["bot"]
    async with AsyncSessionLocal() as session:
        # Chống xử lý trùng nếu SePay gửi lại webhook (retry)
        r = await session.execute(select(Deposit).where(Deposit.sepay_txn_id == txn_id))
        if r.scalar_one_or_none() is not None:
            return web.json_response({"success": True, "message": "duplicate, skipped"}, status=200)

        matched_code = None
        for token in content.split():
            if token.startswith(DEPOSIT_CODE_PREFIX):
                matched_code = token
                break
        if matched_code is None:
            logger.info("ℹ️ Webhook SePay không tìm thấy mã nạp tiền hợp lệ trong nội dung: %s", content)
            return web.json_response({"success": True, "message": "no matching code"}, status=200)

        deposit = await get_pending_deposit_by_code(session, matched_code)
        if deposit is None:
            logger.info("ℹ️ Webhook SePay: không tìm thấy đơn nạp đang chờ với mã %s", matched_code)
            return web.json_response({"success": True, "message": "no pending deposit"}, status=200)
        if amount < deposit.amount:
            logger.warning("⚠️ Webhook SePay: số tiền chuyển (%s) ít hơn yêu cầu (%s) cho mã %s", amount, deposit.amount, matched_code)
            return web.json_response({"success": True, "message": "amount mismatch"}, status=200)

        confirmed = await auto_confirm_deposit(session, deposit.id, txn_id)
        if confirmed is None:
            return web.json_response({"success": True, "message": "already processed"}, status=200)

        user_after = await add_balance(session, confirmed.user_id, confirmed.amount)
        user_tg_id = confirmed.user.telegram_id if confirmed.user else None
        if user_tg_id:
            try:
                await bot.send_message(
                    user_tg_id,
                    f"✅ <b>Nạp tiền tự động thành công!</b>\n\n"
                    f"💵 Cộng: <b>{confirmed.amount:,} VNĐ</b>\n"
                    f"💰 Số dư ví VNĐ: <b>{user_after.balance:,} VNĐ</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        if user_after is not None:
            await maybe_reward_referrer(session, bot, user_after, confirmed.amount)
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"⚡️ <b>Nạp tiền TỰ ĐỘNG</b> — Mã {matched_code}\n"
                    f"👤 {confirmed.user.fullname if confirmed.user else user_tg_id}\n"
                    f"💵 {confirmed.amount:,} VNĐ",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    return web.json_response({"success": True, "message": "confirmed"}, status=200)

async def start_web_server(bot: Bot):
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/", handle_web)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/app", handle_app)
    app.router.add_post("/sepay-webhook", handle_sepay_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"✅ Web Server Keep-Alive đang kích hoạt tại Port: {port}")
    if sepay_enabled():
        logger.info("⚡️ Webhook thanh toán tự động SePay: sẵn sàng tại /sepay-webhook")
    else:
        logger.info("ℹ️ Chưa cấu hình SEPAY_API_KEY/SEPAY_BANK_ACCOUNT — nạp tiền dùng luồng thủ công.")

async def heartbeat_task():
    """Cập nhật heartbeat định kỳ để endpoint /health phản ánh đúng trạng thái bot."""
    while True:
        _last_heartbeat["ts"] = datetime.utcnow()
        logger.debug("💓 Heartbeat OK")
        await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)

async def with_retry(coro_func, *args, what="thao tác", **kwargs):
    """Thử lại một coroutine tối đa RETRY_MAX_ATTEMPTS lần với backoff, dùng cho gọi Telegram API / DB dễ timeout."""
    last_exc = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return await coro_func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            logger.warning("⚠️ %s thất bại (lần %s/%s): %s", what, attempt, RETRY_MAX_ATTEMPTS, exc)
            await asyncio.sleep(RETRY_BASE_DELAY * attempt)
    logger.error("❌ %s thất bại sau %s lần thử: %s", what, RETRY_MAX_ATTEMPTS, last_exc)
    raise last_exc

# ── Tiến Trình Khởi Chạy — Watchdog tự động reconnect, không bao giờ crash hẳn ──
async def run_polling_forever(bot: Bot, dp: Dispatcher):
    """Vòng lặp polling có watchdog: nếu mất kết nối Telegram/DB, tự động chờ và kết nối lại thay vì crash."""
    backoff = RETRY_BASE_DELAY
    while True:
        try:
            logger.info("🤖 Bắt đầu polling Telegram...")
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types(), handle_signals=False)
            break  # dp.start_polling chỉ return khi được dừng chủ động (ví dụ Ctrl+C)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("💥 Polling gặp lỗi, sẽ tự động kết nối lại sau %.1fs: %s", backoff, exc)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)  # tăng dần thời gian chờ, tối đa 60s
            continue

async def main():
    if not BOT_TOKEN:
        logger.error("❌ Thiếu biến môi trường BOT_TOKEN!")
        sys.exit(1)
    if not DATABASE_URL:
        logger.error("❌ Thiếu biến môi trường DATABASE_URL!")
        sys.exit(1)

    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.include_router(router)

    await start_web_server(bot)
    asyncio.create_task(heartbeat_task())

    logger.info("🤖 Bot Shop Đã Sẵn Sàng Trực Tuyến!")
    try:
        await run_polling_forever(bot, dp)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Bot đã dừng theo yêu cầu.")
    except Exception:
        logger.exception("💥 Lỗi nghiêm trọng ngoài dự kiến ở tầng cao nhất — bot vẫn thoát an toàn.")
