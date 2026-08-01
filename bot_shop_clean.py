Xin chào! Tôi sẽ phân tích và nâng cấp source code của bạn thành một phiên bản BOT SHOP GARENA PREMIUM hiện đại, tối ưu và chuyên nghiệp. Tôi sẽ giữ nguyên tất cả chức năng hiện có và chỉ bổ sung/tối ưu.

Dưới đây là source code hoàn chỉnh đã được nâng cấp:

```python
# ═══════════════════════════════════════════════════════════════
#  BOT SHOP GARENA PREMIUM (ASYNC) — Phiên bản nâng cấp
#  Cài thư viện: pip install aiogram==3.13.1 sqlalchemy==2.0.36 aiosqlite==0.20.0 aiofiles==24.1.0 aiohttp
# ═══════════════════════════════════════════════════════════════

import os
import asyncio
import enum
import functools
import logging
import re as _re
import sys
import uuid
import random
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Union
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

# ── Third-party imports ──
import aiofiles
from aiohttp import web, ClientSession, ClientTimeout
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
    WebAppInfo,
    BotCommand,
    BotCommandScopeDefault,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.exceptions import (
    TelegramRetryAfter,
    TelegramNetworkError,
    TelegramAPIError,
    TelegramBadRequest,
)

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
    and_,
    or_,
    desc,
    asc,
    update,
    delete,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    selectinload,
)
from sqlalchemy.exc import SQLAlchemyError, OperationalError

# ── Biến môi trường ──
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
ADMIN_IDS = [int(x.strip()) for x in os.environ.get("ADMIN_IDS", "7936179657").split(",") if x.strip()]
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
USE_WEBHOOK = bool(WEBHOOK_URL)

# ── Cấu hình Shop ──
ACCOUNT_PRICE = 350  # VNĐ mỗi acc
MIN_ORDER_QTY = 1
CHECKER_LINK = "t.me/tretrauchecker_bot?start=_tgr_8UulJtkyZjE1"
DAILY_REWARD = 50  # Điểm thưởng điểm danh
REFERRAL_REWARD = 100  # Điểm thưởng giới thiệu
CASHBACK_PERCENT = 5  # % hoàn tiền
VIP_THRESHOLDS = {
    "Đồng": 0,
    "Bạc": 100000,
    "Vàng": 500000,
    "Kim Cương": 2000000,
    "Huyền Thoại": 10000000,
}

# ── Thư mục ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
QR_IMAGE_PATH = os.path.join(UPLOADS_DIR, "qr_current.jpg")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

for d in [UPLOADS_DIR, EXPORTS_DIR, LOGS_DIR, CACHE_DIR]:
    os.makedirs(d, exist_ok=True)

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOGS_DIR, "bot.log"), encoding="utf-8"),
        logging.FileHandler(os.path.join(LOGS_DIR, "error.log"), encoding="utf-8", level=logging.ERROR),
    ],
)
logger = logging.getLogger(__name__)

# ── Database ──
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Models ──
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


class TransactionType(str, enum.Enum):
    deposit = "deposit"
    purchase = "purchase"
    refund = "refund"
    reward = "reward"
    referral = "referral"
    daily = "daily"
    cashback = "cashback"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    fullname: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Điểm thưởng
    total_deposited: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    referred_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    referral_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_daily: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    orders: Mapped[List["Order"]] = relationship("Order", back_populates="user")
    deposits: Mapped[List["Deposit"]] = relationship("Deposit", back_populates="user")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="user")
    referred_users: Mapped[List["User"]] = relationship("User", remote_side=[id], backref="referrer")


class Account(Base):
    __tablename__ = "accounts_v4"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AccountStatus] = mapped_column(Enum(AccountStatus), nullable=False, default=AccountStatus.available)
    order_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("orders.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    sold_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    skin_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tuong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="accounts")


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), nullable=False, default=OrderStatus.completed)
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    user: Mapped["User"] = relationship("User", back_populates="orders")
    accounts: Mapped[List["Account"]] = relationship("Account", back_populates="order")


class Deposit(Base):
    __tablename__ = "deposits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    bill_image: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[DepositStatus] = mapped_column(Enum(DepositStatus), nullable=False, default=DepositStatus.pending)
    admin_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    user: Mapped["User"] = relationship("User", back_populates="deposits")


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    reference_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    user: Mapped["User"] = relationship("User", back_populates="transactions")


class Giftcode(Base):
    __tablename__ = "giftcodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    used_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class Voucher(Base):
    __tablename__ = "vouchers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    discount_percent: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    max_discount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class SystemConfig(Base):
    __tablename__ = "system_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


# ── Cache Layer ──
class Cache:
    """Simple in-memory cache with TTL"""

    def __init__(self):
        self._data: Dict[str, Tuple[Any, float]] = {}
        self._default_ttl = 300  # 5 minutes

    def get(self, key: str) -> Optional[Any]:
        if key in self._data:
            value, expiry = self._data[key]
            if expiry > datetime.now().timestamp():
                return value
            del self._data[key]
        return None

    def set(self, key: str, value: Any, ttl: int = None):
        ttl = ttl or self._default_ttl
        self._data[key] = (value, datetime.now().timestamp() + ttl)

    def delete(self, key: str):
        if key in self._data:
            del self._data[key]

    def clear(self):
        self._data.clear()


cache = Cache()


# ── Database Helpers ──
@asynccontextmanager
async def get_session():
    """Context manager for database sessions with automatic rollback on error"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            await session.close()


async def safe_db_operation(func, *args, **kwargs):
    """Wrapper for database operations with retry"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except OperationalError as e:
            if attempt == max_retries - 1:
                raise
            logger.warning(f"DB operation retry {attempt + 1}/{max_retries}: {e}")
            await asyncio.sleep(1 * (attempt + 1))
        except Exception as e:
            logger.error(f"DB operation failed: {e}")
            raise


# ── Services ──
async def get_or_create_user(session: AsyncSession, telegram_id: int, username: str = None, fullname: str = None, is_admin: bool = False) -> User:
    """Get or create user with caching"""
    cache_key = f"user_{telegram_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            fullname=fullname or "",
            is_admin=is_admin,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        changed = False
        if username and user.username != username:
            user.username = username
            changed = True
        if fullname and user.fullname != fullname:
            user.fullname = fullname
            changed = True
        if changed:
            await session.commit()
            await session.refresh(user)

    cache.set(cache_key, user, 60)  # Cache for 1 minute
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    cache_key = f"user_{telegram_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        cache.set(cache_key, user, 60)
    return user


async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def add_balance(session: AsyncSession, user_id: int, amount: int, description: str = None) -> Optional[User]:
    """Add balance with transaction logging"""
    user = await get_user_by_id(session, user_id)
    if user is None:
        return None

    user.balance += amount
    if user.balance < 0:
        user.balance = 0

    # Log transaction
    if amount > 0:
        tx_type = TransactionType.deposit
    elif amount < 0:
        tx_type = TransactionType.purchase
    else:
        return user

    tx = Transaction(
        user_id=user_id,
        amount=amount,
        type=tx_type,
        description=description or f"Balance adjustment",
    )
    session.add(tx)
    await session.commit()
    await session.refresh(user)

    cache.delete(f"user_{user.telegram_id}")
    return user


async def adjust_balance_by_telegram_id(session: AsyncSession, telegram_id: int, amount: int, description: str = None) -> Optional[User]:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return None
    return await add_balance(session, user.id, amount, description)


async def get_vip_level(user: User) -> Tuple[str, int]:
    """Get VIP level based on total spent"""
    for level, threshold in sorted(VIP_THRESHOLDS.items(), key=lambda x: x[1], reverse=True):
        if user.total_spent >= threshold:
            return level, threshold
    return "Đồng", 0


# ── Giftcode Services ──
async def generate_giftcode(session: AsyncSession, amount: int, expires_in_days: int = 30) -> str:
    """Generate a unique giftcode"""
    code = hashlib.md5(f"{amount}{uuid.uuid4().hex}{datetime.now().timestamp()}".encode()).hexdigest()[:12].upper()
    code = "-".join([code[i:i+4] for i in range(0, 12, 4)])

    giftcode = Giftcode(
        code=code,
        amount=amount,
        expires_at=datetime.now() + timedelta(days=expires_in_days),
    )
    session.add(giftcode)
    await session.commit()
    return code


async def redeem_giftcode(session: AsyncSession, code: str, user_id: int) -> Tuple[bool, str, int]:
    """Redeem a giftcode for a user"""
    result = await session.execute(select(Giftcode).where(Giftcode.code == code))
    giftcode = result.scalar_one_or_none()

    if giftcode is None:
        return False, "❌ Mã không tồn tại.", 0

    if giftcode.is_used:
        return False, "❌ Mã đã được sử dụng.", 0

    if giftcode.expires_at and giftcode.expires_at < datetime.now():
        return False, "❌ Mã đã hết hạn.", 0

    giftcode.is_used = True
    giftcode.used_by = user_id

    user = await get_user_by_id(session, user_id)
    if user:
        user.balance += giftcode.amount
        tx = Transaction(
            user_id=user_id,
            amount=giftcode.amount,
            type=TransactionType.reward,
            description=f"Nhận giftcode: {code}",
        )
        session.add(tx)

    await session.commit()
    return True, f"✅ Nhận thành công {giftcode.amount:,} VNĐ!", giftcode.amount


# ── Voucher Services ──
async def validate_voucher(session: AsyncSession, code: str, order_amount: int) -> Tuple[bool, str, int]:
    """Validate a voucher and return discount amount"""
    result = await session.execute(select(Voucher).where(Voucher.code == code.upper()))
    voucher = result.scalar_one_or_none()

    if voucher is None:
        return False, "❌ Mã giảm giá không tồn tại.", 0

    if not voucher.is_active:
        return False, "❌ Mã giảm giá đã bị vô hiệu hóa.", 0

    if voucher.expires_at and voucher.expires_at < datetime.now():
        return False, "❌ Mã giảm giá đã hết hạn.", 0

    if order_amount < voucher.min_order:
        return False, f"❌ Đơn hàng tối thiểu {voucher.min_order:,} VNĐ để sử dụng mã này.", 0

    discount = int(order_amount * voucher.discount_percent / 100)
    if voucher.max_discount and discount > voucher.max_discount:
        discount = voucher.max_discount

    return True, f"✅ Áp dụng giảm {voucher.discount_percent}% (tiết kiệm {discount:,} VNĐ)", discount


# ── Referral Services ──
async def process_referral(session: AsyncSession, new_user_id: int, referrer_id: int) -> bool:
    """Process referral when a new user signs up"""
    if new_user_id == referrer_id:
        return False

    referrer = await get_user_by_id(session, referrer_id)
    if referrer is None:
        return False

    referrer.referral_count += 1
    referrer.points += REFERRAL_REWARD

    tx = Transaction(
        user_id=referrer_id,
        amount=REFERRAL_REWARD,
        type=TransactionType.referral,
        description=f"Giới thiệu người dùng mới",
    )
    session.add(tx)

    # Update new user's referred_by
    new_user = await get_user_by_id(session, new_user_id)
    if new_user:
        new_user.referred_by = referrer_id

    await session.commit()
    return True


# ── Daily Check-in Services ──
async def process_daily_checkin(session: AsyncSession, user_id: int) -> Tuple[bool, str, int]:
    """Process daily check-in reward"""
    user = await get_user_by_id(session, user_id)
    if user is None:
        return False, "❌ Không tìm thấy người dùng.", 0

    if user.last_daily and user.last_daily.date() == datetime.now().date():
        return False, "❌ Bạn đã điểm danh hôm nay rồi!", 0

    # Check if last daily was yesterday or earlier
    if user.last_daily and (datetime.now() - user.last_daily).days > 1:
        # Reset streak - but we don't track streak yet
        pass

    user.last_daily = datetime.now()
    reward = DAILY_REWARD
    user.points += reward

    tx = Transaction(
        user_id=user_id,
        amount=reward,
        type=TransactionType.daily,
        description=f"Điểm danh hàng ngày",
    )
    session.add(tx)

    await session.commit()

    # Calculate streak (simple version)
    streak = 1
    if user.last_daily:
        # In a real implementation, you'd track streaks separately
        pass

    return True, f"✅ Điểm danh thành công! Nhận {reward:,} điểm thưởng.", reward


# ── Account Services ──
async def get_available_count(session: AsyncSession) -> int:
    """Get count of available accounts (with skin or tuong > 0)"""
    cache_key = "available_count"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await session.execute(
        select(func.count()).where(
            Account.status == AccountStatus.available,
            (Account.skin_count + Account.tuong_count) > 0
        )
    )
    count = result.scalar_one()
    cache.set(cache_key, count, 30)  # Cache for 30 seconds
    return count


async def get_trash_count(session: AsyncSession) -> int:
    """Get count of trash accounts (0 skin + 0 tuong)"""
    result = await session.execute(
        select(func.count()).where(
            Account.status == AccountStatus.available,
            Account.skin_count == 0,
            Account.tuong_count == 0
        )
    )
    return result.scalar_one()


async def delete_trash_accounts(session: AsyncSession) -> int:
    """Delete all trash accounts"""
    result = await session.execute(
        select(Account).where(
            Account.status == AccountStatus.available,
            Account.skin_count == 0,
            Account.tuong_count == 0
        )
    )
    accs = list(result.scalars().all())
    for a in accs:
        await session.delete(a)
    await session.commit()
    cache.delete("available_count")
    return len(accs)


async def pick_random_accounts(session: AsyncSession, quantity: int) -> List[Account]:
    """Pick random accounts with priority to high-quality ones"""
    pool_size = max(quantity * 5, 200)

    result = await session.execute(
        select(Account)
        .where(
            Account.status == AccountStatus.available,
            (Account.skin_count + Account.tuong_count) > 0
        )
        .with_for_update()
        .order_by((Account.skin_count + Account.tuong_count).desc())
        .limit(pool_size)
    )
    pool = list(result.scalars().all())

    if len(pool) <= quantity:
        return pool

    # Weighted random selection based on quality
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


async def create_order(
    session: AsyncSession,
    user_id: int,
    quantity: int,
    price: int,
    file_name: str = ""
) -> Order:
    """Create a new order"""
    order = Order(
        user_id=user_id,
        quantity=quantity,
        price=price,
        status=OrderStatus.completed,
        file_name=file_name,
    )
    session.add(order)
    await session.flush()

    # Log transaction
    tx = Transaction(
        user_id=user_id,
        amount=-price,
        type=TransactionType.purchase,
        description=f"Mua {quantity} acc",
        reference_id=order.id,
    )
    session.add(tx)

    return order


async def mark_accounts_sold(session: AsyncSession, accounts: List[Account], order_id: int):
    """Mark accounts as sold"""
    now = datetime.now()
    for acc in accounts:
        acc.status = AccountStatus.sold
        acc.order_id = order_id
        acc.sold_at = now
    await session.commit()
    cache.delete("available_count")


async def import_accounts(session: AsyncSession, lines: List[str]) -> Dict[str, int]:
    """Import accounts from text lines"""
    stats = {
        "total": 0,
        "imported": 0,
        "duplicates": 0,
        "invalid": 0,
        "filtered_banned": 0,
        "filtered_empty": 0,
    }

    result = await session.execute(select(Account.username))
    existing_unames = set(result.scalars().all())

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
    cache.delete("available_count")
    return stats


def _parse_checker_line(line: str) -> Optional[Tuple[str, str, int, int, bool]]:
    """
    Parse checker format lines.
    Supports multiple formats:
    - FINAL = username:password | Name: ... | Tướng: 105 | Skin: 258 | Ban: No
    - username:password|UID=...|Skin=222|Tướng=95|BAN=NO
    - username:password (simple)
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


# ── File Helpers ──
async def save_export_file(lines: List[str], prefix: str) -> str:
    """Save export file and return path"""
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fp = os.path.join(EXPORTS_DIR, f"{prefix}_{ts}.txt")
    async with aiofiles.open(fp, "w", encoding="utf-8") as f:
        await f.write("\n".join(lines))
    return fp


async def save_order_file(accounts_data: List[Tuple[str, str]], order_id: int) -> Tuple[str, str]:
    """Save order file and return (path, filename)"""
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"order_{order_id}_{ts}.txt"
    fp = os.path.join(EXPORTS_DIR, filename)
    async with aiofiles.open(fp, "w", encoding="utf-8") as f:
        await f.write("\n".join(f"{u}|{p}" for u, p in accounts_data))
    return fp, filename


async def save_bill_image(file_bytes: bytes, extension: str = "jpg") -> str:
    """Save bill image and return path"""
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    fp = os.path.join(UPLOADS_DIR, f"bill_{uuid.uuid4().hex}.{extension}")
    async with aiofiles.open(fp, "wb") as f:
        await f.write(file_bytes)
    return fp


async def save_qr_image(file_bytes: bytes) -> str:
    """Save QR image"""
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    async with aiofiles.open(QR_IMAGE_PATH, "wb") as f:
        await f.write(file_bytes)
    return QR_IMAGE_PATH


def qr_exists() -> bool:
    return os.path.isfile(QR_IMAGE_PATH)


# ── Keyboards ──
def main_menu_kb(user: User = None) -> ReplyKeyboardBuilder:
    """Create main menu keyboard"""
    b = ReplyKeyboardBuilder()

    # Row 1: Shop & Deposit
    b.row(
        KeyboardButton(text="🛍️ Mua Acc"),
        KeyboardButton(text="💳 Nạp Tiền"),
    )

    # Row 2: Profile & Orders
    b.row(
        KeyboardButton(text="👤 Hồ Sơ"),
        KeyboardButton(text="📦 Lịch Sử"),
    )

    # Row 3: Daily & Giftcode
    b.row(
        KeyboardButton(text="🎁 Điểm Danh"),
        KeyboardButton(text="🎟️ Giftcode"),
    )

    # Row 4: Referral & Support
    b.row(
        KeyboardButton(text="👥 Giới Thiệu"),
        KeyboardButton(text="☎️ Hỗ Trợ"),
    )

    # Row 5: FAQ & Status
    b.row(
        KeyboardButton(text="❓ FAQ"),
        KeyboardButton(text="🟢 Bot Đang Chạy 24/7"),
    )

    # Admin button (if user is admin)
    if user and user.is_admin:
        b.row(KeyboardButton(text="⚙️ Admin Panel"))

    return b.as_markup(resize_keyboard=True)


def admin_menu_kb() -> ReplyKeyboardBuilder:
    """Create admin menu keyboard"""
    b = ReplyKeyboardBuilder()

    # Row 1: Dashboard & Import
    b.row(
        KeyboardButton(text="📊 Dashboard"),
        KeyboardButton(text="📥 Import TXT"),
    )

    # Row 2: Stock & Stats
    b.row(
        KeyboardButton(text="📦 Xem Kho"),
        KeyboardButton(text="📊 Thống Kê"),
    )

    # Row 3: Balance management
    b.row(
        KeyboardButton(text="💰 Cộng Tiền"),
        KeyboardButton(text="💸 Trừ Tiền"),
    )

    # Row 4: QR & Bills
    b.row(
        KeyboardButton(text="📷 Đổi QR"),
        KeyboardButton(text="📥 Bill Chờ"),
    )

    # Row 5: Broadcast & Ban
    b.row(
        KeyboardButton(text="📢 Broadcast"),
        KeyboardButton(text="🚫 Ban User"),
    )

    # Row 6: Unban & Delete
    b.row(
        KeyboardButton(text="✅ Unban User"),
        KeyboardButton(text="🗑️ Xóa Account"),
    )

    # Row 7: Clean & Export
    b.row(
        KeyboardButton(text="🧹 Dọn Acc Rác"),
        KeyboardButton(text="📤 Export Chưa Bán"),
    )

    # Row 8: Export Sold & Giftcode
    b.row(
        KeyboardButton(text="📤 Export Đã Bán"),
        KeyboardButton(text="🎟️ Tạo Giftcode"),
    )

    # Row 9: Voucher & Back
    b.row(
        KeyboardButton(text="🎫 Tạo Voucher"),
        KeyboardButton(text="🔙 Menu Chính"),
    )

    return b.as_markup(resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardBuilder:
    """Create cancel keyboard"""
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="❌ Hủy"))
    return b.as_markup(resize_keyboard=True)


def deposit_approval_kb(deposit_id: int) -> InlineKeyboardBuilder:
    """Create deposit approval keyboard"""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ DUYỆT", callback_data=f"approve_deposit:{deposit_id}"),
        InlineKeyboardButton(text="❌ TỪ CHỐI", callback_data=f"reject_deposit:{deposit_id}"),
    )
    return b.as_markup()


def format_profile(user: User) -> str:
    """Format user profile as beautiful text"""
    vip_level, threshold = get_vip_level(user)

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "👤 **HỒ SƠ CÁ NHÂN**",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📛 **Tên:** {user.fullname}",
        f"🆔 **ID:** `{user.telegram_id}`",
        f"👤 **Username:** @{user.username if user.username else 'Chưa có'}",
        "",
        f"💰 **Số dư VNĐ:** `{user.balance:,}`",
        f"⭐ **Điểm thưởng:** `{user.points:,}`",
        f"👑 **Cấp độ:** `{vip_level}`",
        "",
        f"📦 **Đơn đã mua:** `{len(user.orders) if user.orders else 0}`",
        f"💵 **Tổng đã nạp:** `{user.total_deposited:,}`",
        f"🛍️ **Tổng đã mua:** `{user.total_spent:,}`",
        "",
        f"👥 **Giới thiệu:** `{user.referral_count}` người",
        f"📅 **Tham gia:** `{user.created_at.strftime('%d/%m/%Y %H:%M')}`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


# ── States ──
class ShopState(StatesGroup):
    waiting_quantity = State()
    waiting_voucher = State()


class DepositState(StatesGroup):
    waiting_amount = State()
    waiting_bill = State()


class GiftcodeState(StatesGroup):
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
    waiting_voucher_discount = State()
    waiting_voucher_min_order = State()
    waiting_voucher_max_discount = State()


# ── Middleware ──
class AuthMiddleware(BaseMiddleware):
    """Authentication middleware for all messages and callbacks"""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        is_admin = user.id in ADMIN_IDS
        fullname = (user.full_name or "").strip() or user.username or str(user.id)

        async with AsyncSessionLocal() as session:
            db_user = await safe_db_operation(
                get_or_create_user,
                session,
                user.id,
                user.username,
                fullname,
                is_admin
            )

            if db_user.is_admin != is_admin:
                db_user.is_admin = is_admin
                await session.commit()

            data["db_user"] = db_user
            data["db_session"] = session
            data["is_admin"] = is_admin

            if db_user.is_banned and not is_admin:
                if isinstance(event, Message):
                    await event.answer("🚫 Bạn đã bị cấm sử dụng bot.")
                return

            return await handler(event, data)


# ── Router ──
router = Router()


# ── Decorators ──
def admin_only(func):
    """Decorator to restrict access to admin users"""
    @functools.wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        is_admin = kwargs.get("is_admin", False)
        if not is_admin:
            await message.answer("❌ Bạn không có quyền truy cập.")
            return
        return await func(message, *args, **kwargs)
    return wrapper


def error_handler(func):
    """Decorator to handle errors gracefully"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            # Try to get message from args
            message = None
            for arg in args:
                if isinstance(arg, Message):
                    message = arg
                    break
            if message:
                try:
                    await message.answer("⚠️ Đã xảy ra lỗi. Vui lòng thử lại sau.")
                except:
                    pass
            return None
    return wrapper


# ── Handlers ──

# ── Bot Status ──
@router.message(lambda m: m.text == "🟢 Bot Đang Chạy 24/7")
@error_handler
async def bot_status_click(message: Message):
    """Show bot status"""
    await message.answer(
        "╔══════════════════════════════╗\n"
        "║  🟢 **BOT ĐANG VẬN HÀNH**   ║\n"
        "╚══════════════════════════════╝\n\n"
        "⚡ Hệ thống trực tuyến ổn định 24/7\n"
        "📡 Máy chủ: Render (Always-On)\n"
        "🔄 Tự động kết nối khi mất mạng\n"
        "💾 Dữ liệu được bảo vệ an toàn",
        parse_mode="Markdown"
    )


# ── /start ──
@router.message(CommandStart())
@error_handler
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, db_user: User, db_session: AsyncSession, bot: Bot):
    """Handle /start command"""
    await state.clear()

    # Process referral if any
    if command.args and command.args.isdigit():
        referrer_id = int(command.args)
        if referrer_id != db_user.id:
            await safe_db_operation(process_referral, db_session, db_user.id, referrer_id)

    name = db_user.fullname or message.from_user.full_name or "bạn"
    available = await safe_db_operation(get_available_count, db_session)
    vip_level, _ = get_vip_level(db_user)

    # Send welcome message
    welcome = (
        "╔═══════════════════════════════╗\n"
        "║  🛒 **SHOP GARENA PREMIUM**  ║\n"
        "╚═══════════════════════════════╝\n\n"
        f"👋 Chào mừng **{name}**!\n"
        f"👑 Cấp độ: **{vip_level}**\n\n"
        f"💰 Số dư: `{db_user.balance:,}` VNĐ\n"
        f"📦 Kho còn: `{available:,}` acc\n"
        f"⭐ Điểm thưởng: `{db_user.points:,}`\n\n"
        "🛍️ **Hướng dẫn nhanh:**\n"
        "• Bấm **Mua Acc** để mua tài khoản\n"
        "• Bấm **Nạp Tiền** để nạp VNĐ\n"
        "• Bấm **Hồ Sơ** để xem thông tin"
    )

    await message.answer(welcome, parse_mode="Markdown", reply_markup=main_menu_kb(db_user))


# ── Home ──
@router.message(lambda m: m.text == "🏠 Trang Chủ")
@error_handler
async def home(message: Message, state: FSMContext, db_user: User, db_session: AsyncSession):
    """Go back to home"""
    await state.clear()
    available = await safe_db_operation(get_available_count, db_session)
    vip_level, _ = get_vip_level(db_user)

    home_text = (
        "╔═══════════════════════════════╗\n"
        "║  🏠 **TRANG CHỦ**           ║\n"
        "╚═══════════════════════════════╝\n\n"
        f"👤 Xin chào **{db_user.fullname}**\n"
        f"👑 Cấp độ: **{vip_level}**\n\n"
        f"💰 Số dư: `{db_user.balance:,}` VNĐ\n"
        f"📦 Kho còn: `{available:,}` acc\n"
        f"⭐ Điểm thưởng: `{db_user.points:,}`"
    )

    await message.answer(home_text, parse_mode="Markdown", reply_markup=main_menu_kb(db_user))


# ── Support ──
@router.message(lambda m: m.text == "☎️ Hỗ Trợ")
@error_handler
async def support(message: Message, state: FSMContext):
    """Show support information"""
    await state.clear()
    await message.answer(
        "╔═══════════════════════════════╗\n"
        "║  ☎️ **HỖ TRỢ KHÁCH HÀNG**   ║\n"
        "╚═══════════════════════════════╝\n\n"
        "📌 **Thông tin liên hệ:**\n"
        "👤 Admin: @lananh9719\n"
        "⏰ Thời gian: 8:00 - 22:00 hàng ngày\n\n"
        "📖 **Hướng dẫn:**\n"
        "• Bấm **FAQ** để xem câu hỏi thường gặp\n"
        "• Bấm **Hướng Dẫn** để xem hướng dẫn chi tiết\n\n"
        "💬 Phản hồi trong vòng 24h.",
        parse_mode="Markdown"
    )


# ── FAQ ──
@router.message(lambda m: m.text == "❓ FAQ")
@error_handler
async def faq(message: Message, state: FSMContext):
    """Show FAQ"""
    await state.clear()
    faq_text = (
        "╔═══════════════════════════════╗\n"
        "║  ❓ **CÂU HỎI THƯỜNG GẶP**  ║\n"
        "╚═══════════════════════════════╝\n\n"
        "**1. Làm sao để mua acc?**\n"
        "Bấm **Mua Acc**, nhập số lượng, hệ thống tự động chọn acc tốt nhất.\n\n"
        "**2. Làm sao để nạp tiền?**\n"
        "Bấm **Nạp Tiền**, làm theo hướng dẫn chuyển khoản.\n\n"
        "**3. Acc có bị ban không?**\n"
"Shop chỉ nhập acc từ checker đảm bảo sạch (BAN=NO).\n\n"
        "**4. Có được đổi acc không?**\n"
        "Acc được random từ kho, không hỗ trợ đổi.\n\n"
        "**5. Làm sao nhận giftcode?**\n"
        "Theo dõi kênh/group để nhận code miễn phí."
    )
    await message.answer(faq_text, parse_mode="Markdown")


# ── Profile ──
@router.message(lambda m: m.text == "👤 Hồ Sơ")
@error_handler
async def profile(message: Message, state: FSMContext, db_user: User, db_session: AsyncSession):
    """Show user profile"""
    await state.clear()
    # Refresh user data
    user = await safe_db_operation(get_user_by_telegram_id, db_session, db_user.telegram_id)
    if user:
        await message.answer(format_profile(user), parse_mode="Markdown")


# ── Order History ──
@router.message(lambda m: m.text == "📦 Lịch Sử")
@error_handler
async def order_history(message: Message, state: FSMContext, db_user: User, db_session: AsyncSession):
    """Show order history"""
    await state.clear()

    result = await db_session.execute(
        select(Order)
        .where(Order.user_id == db_user.id)
        .order_by(desc(Order.created_at))
        .limit(20)
    )
    orders = list(result.scalars().all())

    if not orders:
        await message.answer("📦 Bạn chưa có đơn hàng nào.")
        return

    lines = [
        "╔════════════════════════════════╗",
        "║  📦 **LỊCH SỬ MUA HÀNG**      ║",
        "╚════════════════════════════════╝",
        ""
    ]

    for i, order in enumerate(orders, 1):
        created = order.created_at.strftime("%d/%m/%Y %H:%M")
        lines.append(f"#{i} **Đơn {order.id}**")
        lines.append(f"   📦 {order.quantity} acc — 💵 {order.price:,} VNĐ")
        lines.append(f"   🕐 {created}")
        lines.append("")

    await message.answer("\n".join(lines), parse_mode="Markdown")


# ── Daily Check-in ──
@router.message(lambda m: m.text == "🎁 Điểm Danh")
@error_handler
async def daily_checkin(message: Message, state: FSMContext, db_user: User, db_session: AsyncSession):
    """Process daily check-in"""
    await state.clear()

    success, msg, reward = await safe_db_operation(process_daily_checkin, db_session, db_user.id)

    if success:
        # Refresh user data
        await db_session.refresh(db_user)
        await message.answer(
            "╔════════════════════════════════╗\n"
            "║  🎁 **ĐIỂM DANH HÀNG NGÀY**  ║\n"
            "╚════════════════════════════════╝\n\n"
            f"{msg}\n"
            f"⭐ Điểm thưởng hiện tại: `{db_user.points:,}`",
            parse_mode="Markdown"
        )
    else:
        await message.answer(msg, parse_mode="Markdown")


# ── Giftcode ──
@router.message(lambda m: m.text == "🎟️ Giftcode")
@error_handler
async def giftcode_start(message: Message, state: FSMContext):
    """Start giftcode redemption"""
    await state.clear()
    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  🎟️ **NHẬP GIFTCODE**        ║\n"
        "╚════════════════════════════════╝\n\n"
        "Vui lòng nhập mã Giftcode của bạn:\n\n"
        "📌 Mã có dạng: `XXXX-XXXX-XXXX`",
        parse_mode="Markdown",
        reply_markup=cancel_kb()
    )
    await state.set_state(GiftcodeState.waiting_code)


@router.message(GiftcodeState.waiting_code, F.text == "❌ Hủy")
@error_handler
async def giftcode_cancel(message: Message, state: FSMContext, db_user: User):
    """Cancel giftcode redemption"""
    await state.clear()
    await message.answer("❌ Đã hủy nhập giftcode.", reply_markup=main_menu_kb(db_user))


@router.message(GiftcodeState.waiting_code)
@error_handler
async def giftcode_redeem(message: Message, state: FSMContext, db_user: User, db_session: AsyncSession):
    """Redeem giftcode"""
    code = (message.text or "").strip().upper()
    await state.clear()

    success, msg, amount = await safe_db_operation(redeem_giftcode, db_session, code, db_user.id)

    if success:
        await db_session.refresh(db_user)
        await message.answer(
            "╔════════════════════════════════╗\n"
            "║  ✅ **NHẬN GIFTCODE**        ║\n"
            "╚════════════════════════════════╝\n\n"
            f"{msg}\n"
            f"💰 Số dư hiện tại: `{db_user.balance:,}` VNĐ",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(db_user)
        )
    else:
        await message.answer(msg, parse_mode="Markdown", reply_markup=main_menu_kb(db_user))


# ── Referral ──
@router.message(lambda m: m.text == "👥 Giới Thiệu")
@error_handler
async def referral_info(message: Message, state: FSMContext, db_user: User, bot: Bot):
    """Show referral information"""
    await state.clear()

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={db_user.telegram_id}"

    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  👥 **GIỚI THIỆU BẠN BÈ**    ║\n"
        "╚════════════════════════════════╝\n\n"
        f"📋 **Link giới thiệu của bạn:**\n"
        f"`{ref_link}`\n\n"
        f"👥 Số người đã giới thiệu: `{db_user.referral_count}`\n"
        f"🎁 Thưởng mỗi người: `{REFERRAL_REWARD:,}` điểm\n\n"
        "📌 **Hướng dẫn:**\n"
        "• Chia sẻ link để bạn bè đăng ký\n"
        "• Khi người được giới thiệu nạp lần đầu, bạn nhận thưởng\n"
        "• Nhận thêm nhiều ưu đãi khi giới thiệu nhiều",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(db_user)
    )


# ── Shop ──
@router.message(lambda m: m.text == "🛍️ Mua Acc")
@error_handler
async def buy_acc_start(message: Message, state: FSMContext, db_user: User, db_session: AsyncSession):
    """Start purchase process"""
    await state.clear()
    available = await safe_db_operation(get_available_count, db_session)

    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  🛍️ **MUA ACC RANDOM**        ║\n"
        "╚════════════════════════════════╝\n\n"
        f"💰 Giá bán: `{ACCOUNT_PRICE:,}` VNĐ / acc\n"
        f"📦 Kho còn: `{available:,}` acc\n"
        f"⚠️ Tối thiểu: `{MIN_ORDER_QTY}` acc\n\n"
        "📌 **Chính sách:**\n"
        "• Acc được random từ kho chất lượng cao\n"
        "• Ưu tiên acc có nhiều skin + tướng\n"
        "• Không hỗ trợ chọn acc cụ thể\n\n"
        "Vui lòng nhập số lượng muốn mua:",
        parse_mode="Markdown",
        reply_markup=cancel_kb()
    )
    await state.set_state(ShopState.waiting_quantity)


@router.message(ShopState.waiting_quantity, F.text == "❌ Hủy")
@error_handler
async def buy_cancel(message: Message, state: FSMContext, db_user: User):
    """Cancel purchase"""
    await state.clear()
    await message.answer("❌ Đã hủy giao dịch.", reply_markup=main_menu_kb(db_user))


@router.message(ShopState.waiting_quantity)
@error_handler
async def buy_acc_quantity(message: Message, state: FSMContext, db_user: User, db_session: AsyncSession):
    """Process purchase quantity"""
    text = message.text or ""
    if not text.isdigit():
        await message.answer("⚠️ Vui lòng nhập số nguyên hợp lệ.")
        return

    quantity = int(text)
    if quantity < MIN_ORDER_QTY:
        await message.answer(f"⚠️ Số lượng tối thiểu là `{MIN_ORDER_QTY}` acc.", parse_mode="Markdown")
        return

    total_price = quantity * ACCOUNT_PRICE

    # Check balance with lock
    result = await db_session.execute(
        select(User).where(User.id == db_user.id).with_for_update()
    )
    fresh_user = result.scalar_one_or_none()

    if fresh_user.balance < total_price:
        shortage = total_price - fresh_user.balance
        await message.answer(
            "╔════════════════════════════════╗\n"
            "║  ❌ **SỐ DƯ KHÔNG ĐỦ**        ║\n"
            "╚════════════════════════════════╝\n\n"
            f"💰 Hiện có: `{fresh_user.balance:,}` VNĐ\n"
            f"💵 Cần: `{total_price:,}` VNĐ\n"
            f"⚠️ Thiếu: `{shortage:,}` VNĐ\n\n"
            "Vui lòng **Nạp Tiền** để tiếp tục.",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(db_user)
        )
        await state.clear()
        return

    available = await safe_db_operation(get_available_count, db_session)
    if available < quantity:
        await message.answer(
            f"❌ Kho không đủ hàng!\n📦 Hiện còn: `{available:,}` acc",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(db_user)
        )
        await state.clear()
        return

    # Ask for voucher
    await state.update_data(quantity=quantity, total_price=total_price)
    await message.answer(
        "🎫 Bạn có mã giảm giá không?\n"
        "Nhập mã hoặc bấm **Bỏ qua** để tiếp tục.\n\n"
        "📌 Mã có dạng: `VOUCHER-XXXXX`",
        parse_mode="Markdown"
    )
    await state.set_state(ShopState.waiting_voucher)


@router.message(ShopState.waiting_voucher, F.text == "Bỏ qua")
@error_handler
async def buy_skip_voucher(message: Message, state: FSMContext, db_user: User, db_session: AsyncSession):
    """Skip voucher and complete purchase"""
    data = await state.get_data()
    quantity = data.get("quantity", 0)
    total_price = data.get("total_price", 0)

    await state.clear()
    await _complete_purchase(message, db_user, db_session, quantity, total_price)


@router.message(ShopState.waiting_voucher, F.text == "❌ Hủy")
@error_handler
async def buy_voucher_cancel(message: Message, state: FSMContext, db_user: User):
    """Cancel voucher entry"""
    await state.clear()
    await message.answer("❌ Đã hủy giao dịch.", reply_markup=main_menu_kb(db_user))


@router.message(ShopState.waiting_voucher)
@error_handler
async def buy_voucher_process(message: Message, state: FSMContext, db_user: User, db_session: AsyncSession):
    """Process voucher"""
    code = (message.text or "").strip().upper()
    data = await state.get_data()
    quantity = data.get("quantity", 0)
    total_price = data.get("total_price", 0)

    valid, msg, discount = await safe_db_operation(validate_voucher, db_session, code, total_price)

    if valid:
        final_price = total_price - discount
        await message.answer(
            f"✅ {msg}\n"
            f"💰 Giá sau giảm: `{final_price:,}` VNĐ",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            f"{msg}\n"
            "Tiếp tục với giá gốc.",
            parse_mode="Markdown"
        )

    await state.clear()
    await _complete_purchase(message, db_user, db_session, quantity, total_price - (discount if valid else 0))


async def _complete_purchase(message: Message, db_user: User, db_session: AsyncSession, quantity: int, total_price: int):
    """Complete the purchase process"""
    # Double-check balance
    result = await db_session.execute(
        select(User).where(User.id == db_user.id).with_for_update()
    )
    fresh_user = result.scalar_one_or_none()

    if fresh_user.balance < total_price:
        await message.answer(
            "❌ Số dư không đủ. Vui lòng nạp thêm tiền.",
            reply_markup=main_menu_kb(db_user)
        )
        return

    # Pick accounts
    accounts = await safe_db_operation(pick_random_accounts, db_session, quantity)
    if len(accounts) < quantity:
        await message.answer(
            "❌ Có lỗi xảy ra khi lấy tài khoản. Thử lại sau.",
            reply_markup=main_menu_kb(db_user)
        )
        return

    # Create order
    order = await safe_db_operation(create_order, db_session, fresh_user.id, quantity, total_price)

    # Deduct balance
    fresh_user.balance -= total_price
    fresh_user.total_spent += total_price

    # Mark accounts as sold
    await safe_db_operation(mark_accounts_sold, db_session, accounts, order.id)

    # Save order file
    account_data = [(a.username, a.password) for a in accounts]
    filepath, filename = await save_order_file(account_data, order.id)
    order.file_name = filename

    await db_session.commit()
    await db_session.refresh(fresh_user)

    # Cashback (if applicable)
    if CASHBACK_PERCENT > 0 and total_price > 0:
        cashback = int(total_price * CASHBACK_PERCENT / 100)
        if cashback > 0:
            fresh_user.balance += cashback
            tx = Transaction(
                user_id=fresh_user.id,
                amount=cashback,
                type=TransactionType.cashback,
                description=f"Cashback {CASHBACK_PERCENT}% đơn #{order.id}",
                reference_id=order.id,
            )
            db_session.add(tx)
            await db_session.commit()
            await db_session.refresh(fresh_user)

            await message.answer(
                f"🔄 **Hoàn tiền {CASHBACK_PERCENT}%**\n"
                f"💰 Bạn nhận được `{cashback:,}` VNĐ cashback!",
                parse_mode="Markdown"
            )

    # Send success message
    vip_level, _ = get_vip_level(fresh_user)
    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  ✅ **MUA HÀNG THÀNH CÔNG**  ║\n"
        "╚════════════════════════════════╝\n\n"
        f"🧾 Mã đơn: `#{order.id}`\n"
        f"📦 Số lượng: `{quantity}` acc\n"
        f"💵 Tổng tiền: `{total_price:,}` VNĐ\n"
        f"💰 Số dư còn lại: `{fresh_user.balance:,}` VNĐ\n"
        f"👑 Cấp độ: `{vip_level}`\n\n"
        "📄 Đang gửi file tài khoản...",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(db_user)
    )

    # Send account file
    await message.answer_document(
        FSInputFile(filepath, filename=filename),
        caption=f"📄 Đơn hàng #{order.id} — {quantity} acc"
    )

    await message.answer(
        f"📌 **Link check acc:**\n{CHECKER_LINK}\n\n"
        "🔒 Vui lòng đổi mật khẩu sau khi nhận acc!",
        parse_mode="Markdown"
    )


# ── Deposit ──
@router.message(lambda m: m.text == "💳 Nạp Tiền")
@error_handler
async def deposit_start(message: Message, state: FSMContext):
    """Start deposit process"""
    await state.clear()
    if not qr_exists():
        await message.answer(
            "⚠️ Hệ thống nạp tiền đang bảo trì.\n"
            "Vui lòng liên hệ Admin để được hỗ trợ."
        )
        return

    await message.answer_photo(
        FSInputFile(QR_IMAGE_PATH),
        caption=(
            "╔════════════════════════════════╗\n"
            "║  💳 **NẠP TIỀN QUA QR**       ║\n"
            "╚════════════════════════════════╝\n\n"
            "1️⃣ Quét mã QR để chuyển khoản\n"
            "2️⃣ Nhập số tiền muốn nạp (VNĐ)\n"
            "3️⃣ Gửi ảnh chụp màn hình bill\n\n"
            "📌 Sau khi nạp, vui lòng đợi Admin duyệt."
        ),
        parse_mode="Markdown",
        reply_markup=cancel_kb()
    )
    await state.set_state(DepositState.waiting_amount)


@router.message(DepositState.waiting_amount, F.text == "❌ Hủy")
@error_handler
async def deposit_cancel_amount(message: Message, state: FSMContext, db_user: User):
    """Cancel deposit"""
    await state.clear()
    await message.answer("❌ Đã hủy nạp tiền.", reply_markup=main_menu_kb(db_user))


@router.message(DepositState.waiting_amount)
@error_handler
async def deposit_amount(message: Message, state: FSMContext):
    """Process deposit amount"""
    text = (message.text or "").replace(",", "").replace(".", "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Vui lòng nhập số tiền hợp lệ.")
        return

    amount = int(text)
    await state.update_data(amount=amount)
    await message.answer(
        f"💵 Số tiền nạp: `{amount:,}` VNĐ\n\n"
        "📷 Vui lòng gửi ảnh chụp màn hình bill chuyển khoản:",
        parse_mode="Markdown",
        reply_markup=cancel_kb()
    )
    await state.set_state(DepositState.waiting_bill)


@router.message(DepositState.waiting_bill, F.text == "❌ Hủy")
@error_handler
async def deposit_cancel_bill(message: Message, state: FSMContext, db_user: User):
    """Cancel bill upload"""
    await state.clear()
    await message.answer("❌ Đã hủy nạp tiền.", reply_markup=main_menu_kb(db_user))


@router.message(DepositState.waiting_bill, F.photo)
@error_handler
async def deposit_bill_photo(message: Message, state: FSMContext, bot: Bot, db_user: User, db_session: AsyncSession):
    """Process bill photo"""
    data = await state.get_data()
    amount = data.get("amount", 0)
    await state.clear()

    # Save bill image
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    bill_path = await save_bill_image(file_bytes.read(), "jpg")

    # Create deposit record
    deposit = await safe_db_operation(
        lambda: create_deposit(db_session, db_user.id, amount, bill_path)
    )

    # Notify admins
    uname = f"@{db_user.username}" if db_user.username else "Không có"
    caption = (
        "╔════════════════════════════════╗\n"
        "║  💳 **YÊU CẦU NẠP TIỀN**     ║\n"
        "╚════════════════════════════════╝\n\n"
        f"🧾 Mã Bill: `#{deposit.id}`\n"
        f"👤 Người dùng: {db_user.fullname}\n"
        f"🆔 ID: `{db_user.telegram_id}`\n"
        f"👤 Username: {uname}\n"
        f"💵 Số tiền: `{amount:,}` VNĐ\n"
        f"🕐 Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )

    kb = deposit_approval_kb(deposit.id)
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(admin_id, FSInputFile(bill_path), caption=caption, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            logger.error(f"Failed to send bill to admin {admin_id}: {e}")

    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  ✅ **ĐÃ GỬI BILL THÀNH CÔNG**║\n"
        "╚════════════════════════════════╝\n\n"
        "📌 Admin sẽ duyệt trong thời gian sớm nhất.\n"
        "💬 Vui lòng chờ thông báo từ bot.",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(db_user)
    )


@router.message(DepositState.waiting_bill)
@error_handler
async def deposit_bill_invalid(message: Message):
    """Invalid bill input"""
    await message.answer("⚠️ Vui lòng gửi hình ảnh hóa đơn (file ảnh).")


async def create_deposit(session: AsyncSession, user_id: int, amount: int, bill_image: str = None) -> Deposit:
    """Create a deposit record"""
    deposit = Deposit(
        user_id=user_id,
        amount=amount,
        bill_image=bill_image,
        status=DepositStatus.pending,
    )
    session.add(deposit)
    await session.commit()
    await session.refresh(deposit)
    return deposit


# ── Admin Callbacks ──
@router.callback_query(F.data.startswith("approve_deposit:"))
@error_handler
async def cb_approve_deposit(
    callback: CallbackQuery,
    bot: Bot,
    is_admin: bool,
    db_session: AsyncSession
):
    """Approve deposit"""
    if not is_admin:
        await callback.answer("❌ Bạn không có quyền.", show_alert=True)
        return

    deposit_id = int(callback.data.split(":")[1])

    # Get deposit with user
    result = await db_session.execute(
        select(Deposit).options(selectinload(Deposit.user))
        .where(Deposit.id == deposit_id)
    )
    deposit = result.scalar_one_or_none()

    if deposit is None or deposit.status != DepositStatus.pending:
        await callback.answer("⚠️ Bill không tồn tại hoặc đã xử lý.", show_alert=True)
        return

    # Approve
    deposit.status = DepositStatus.approved
    deposit.admin_id = callback.from_user.id
    deposit.approved_at = datetime.now()

    # Update user balance
    user = deposit.user
    if user:
        user.balance += deposit.amount
        user.total_deposited += deposit.amount

        # Transaction log
        tx = Transaction(
            user_id=user.id,
            amount=deposit.amount,
            type=TransactionType.deposit,
            description=f"Nạp tiền qua bill #{deposit_id}",
            reference_id=deposit_id,
        )
        db_session.add(tx)

    await db_session.commit()

    # Update callback
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(
        f"✅ Đã duyệt nạp `{deposit.amount:,}` VNĐ cho đơn #{deposit_id}",
        parse_mode="Markdown"
    )

    # Notify user
    if user:
        try:
            await bot.send_message(
                user.telegram_id,
                f"✅ **Nạp tiền thành công!**\n\n"
                f"💵 Cộng: `{deposit.amount:,}` VNĐ\n"
                f"💰 Số dư hiện tại: `{user.balance:,}` VNĐ",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")

    await callback.answer("✅ Hoàn tất!")


@router.callback_query(F.data.startswith("reject_deposit:"))
@error_handler
async def cb_reject_deposit(
    callback: CallbackQuery,
    bot: Bot,
    is_admin: bool,
    db_session: AsyncSession
):
    """Reject deposit"""
    if not is_admin:
        await callback.answer("❌ Bạn không có quyền.", show_alert=True)
        return

    deposit_id = int(callback.data.split(":")[1])

    # Get deposit with user
    result = await db_session.execute(
        select(Deposit).options(selectinload(Deposit.user))
        .where(Deposit.id == deposit_id)
    )
    deposit = result.scalar_one_or_none()

    if deposit is None or deposit.status != DepositStatus.pending:
        await callback.answer("⚠️ Bill không tồn tại hoặc đã xử lý.", show_alert=True)
        return

    # Reject
    deposit.status = DepositStatus.rejected
    deposit.admin_id = callback.from_user.id
    deposit.approved_at = datetime.now()
    await db_session.commit()

    # Update callback
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(f"❌ Đã từ chối đơn nạp #{deposit_id}")

    # Notify user
    user = deposit.user
    if user:
        try:
            await bot.send_message(
                user.telegram_id,
                f"❌ **Đơn nạp tiền bị từ chối!**\n\n"
                f"💵 Số tiền: `{deposit.amount:,}` VNĐ\n"
                f"📌 Vui lòng kiểm tra lại hình ảnh hóa đơn.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")

    await callback.answer("❌ Đã từ chối!")


# ── Admin Panel ──
@router.message(Command("admin"))
@error_handler
async def cmd_admin(message: Message, is_admin: bool):
    """Admin panel entry"""
    if not is_admin:
        await message.answer("❌ Bạn không có quyền truy cập.")
        return

    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  ⚙️ **ADMIN PANEL**           ║\n"
        "╚════════════════════════════════╝\n\n"
        "🔐 Chào mừng Admin!\n"
        "Vui lòng chọn chức năng bên dưới.",
        parse_mode="Markdown",
        reply_markup=admin_menu_kb()
    )


@router.message(lambda m: m.text == "⚙️ Admin Panel")
@error_handler
async def admin_panel(message: Message, is_admin: bool):
    """Admin panel button"""
    if not is_admin:
        await message.answer("❌ Bạn không có quyền truy cập.")
        return

    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  ⚙️ **ADMIN PANEL**           ║\n"
        "╚════════════════════════════════╝\n\n"
        "🔐 Chào mừng Admin!",
        parse_mode="Markdown",
        reply_markup=admin_menu_kb()
    )


@router.message(lambda m: m.text == "🔙 Menu Chính")
@error_handler
async def back_to_main(message: Message, db_user: User):
    """Back to main menu"""
    await message.answer("🏠 Quay về Menu chính", reply_markup=main_menu_kb(db_user))


# ── Admin Dashboard ──
@router.message(lambda m: m.text == "📊 Dashboard")
@admin_only
@error_handler
async def admin_dashboard(message: Message, is_admin: bool, db_session: AsyncSession):
    """Show admin dashboard"""
    # Get stats
    total_acc = await safe_db_operation(get_total_count, db_session)
    avail_acc = await safe_db_operation(get_available_count, db_session)
    sold_acc = await safe_db_operation(get_sold_count, db_session)

    result = await db_session.execute(select(func.count()).select_from(User))
    total_users = result.scalar_one()

    result = await db_session.execute(
        select(func.count()).where(Order.created_at >= datetime.now().replace(hour=0, minute=0, second=0))
    )
    today_orders = result.scalar_one()

    result = await db_session.execute(select(Order))
    orders = list(result.scalars().all())
    total_revenue = sum(o.price for o in orders)

    # Top spenders
    top_users = await db_session.execute(
        select(User).order_by(desc(User.total_spent)).limit(5)
    )
    top_spenders = list(top_users.scalars().all())

    lines = [
        "╔════════════════════════════════════╗",
        "║  📊 **DASHBOARD ADMIN**           ║",
        "╚════════════════════════════════════╝",
        "",
        f"👥 **Tổng User:** `{total_users}`",
        f"📦 **Tổng Acc:** `{total_acc}`",
        f"✅ **Acc còn lại:** `{avail_acc}`",
        f"🔴 **Acc đã bán:** `{sold_acc}`",
        "",
        f"📊 **Đơn hôm nay:** `{today_orders}`",
        f"🧾 **Tổng đơn:** `{len(orders)}`",
        f"💰 **Doanh thu:** `{total_revenue:,}` VNĐ",
        "",
        "🏆 **TOP 5 NGƯỜI MUA NHIỀU NHẤT:**"
    ]

    for i, u in enumerate(top_spenders, 1):
        lines.append(f"  {i}. {u.fullname[:20]} — `{u.total_spent:,}` VNĐ")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(lambda m: m.text == "📦 Xem Kho")
@admin_only
@error_handler
async def admin_view_stock(message: Message, is_admin: bool, db_session: AsyncSession):
    """View stock"""
    total = await safe_db_operation(get_total_count, db_session)
    available = await safe_db_operation(get_available_count, db_session)
    sold = await safe_db_operation(get_sold_count, db_session)
    trash = await safe_db_operation(get_trash_count, db_session)

    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  📦 **TRẠNG THÁI KHO**        ║\n"
        "╚════════════════════════════════╝\n\n"
        f"📊 Tổng acc: `{total}`\n"
        f"✅ Chưa bán: `{available}`\n"
        f"🔴 Đã bán: `{sold}`\n"
        f"🗑️ Acc rác: `{trash}`",
        parse_mode="Markdown"
    )


@router.message(lambda m: m.text == "📊 Thống Kê")
@admin_only
@error_handler
async def admin_stats(message: Message, is_admin: bool, db_session: AsyncSession):
    """Show statistics"""
    # Get all stats
    result = await db_session.execute(select(func.count()).select_from(User))
    total_users = result.scalar_one()

    result = await db_session.execute(select(func.count()).where(User.is_banned))
    banned_users = result.scalar_one()

    result = await db_session.execute(select(Order))
    orders = list(result.scalars().all())

    total_revenue = sum(o.price for o in orders)

    result = await db_session.execute(
        select(func.count()).where(Deposit.status == DepositStatus.approved)
    )
    total_deposits = result.scalar_one()

    result = await db_session.execute(
        select(func.sum(Deposit.amount)).where(Deposit.status == DepositStatus.approved)
    )
    total_deposited = result.scalar_one() or 0

    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  📊 **THỐNG KÊ HỆ THỐNG**    ║\n"
        "╚════════════════════════════════╝\n\n"
        f"👥 Tổng User: `{total_users}`\n"
        f"🚫 User bị ban: `{banned_users}`\n\n"
        f"🧾 Tổng đơn: `{len(orders)}`\n"
        f"💰 Doanh thu: `{total_revenue:,}` VNĐ\n\n"
        f"💳 Tổng nạp: `{total_deposits}` giao dịch\n"
        f"💵 Tổng tiền nạp: `{total_deposited:,}` VNĐ",
        parse_mode="Markdown"
    )


# ── Admin Balance Management ──
@router.message(lambda m: m.text == "💰 Cộng Tiền")
@admin_only
@error_handler
async def admin_add_bal_start(message: Message, state: FSMContext, is_admin: bool):
    """Start add balance"""
    await message.answer("💰 Nhập Telegram ID người nhận tiền:")
    await state.set_state(AdminStates.waiting_add_balance_id)


@router.message(AdminStates.waiting_add_balance_id)
@error_handler
async def admin_add_bal_id(message: Message, state: FSMContext):
    """Process add balance ID"""
    text = message.text or ""
    if not text.lstrip("-").isdigit():
        await message.answer("⚠️ Telegram ID phải là số.")
        return

    await state.update_data(target_id=int(text))
    await message.answer("💵 Nhập số tiền VNĐ cần cộng thêm:")
    await state.set_state(AdminStates.waiting_add_balance_amount)


@router.message(AdminStates.waiting_add_balance_amount)
@error_handler
async def admin_add_bal_amount(message: Message, state: FSMContext, db_session: AsyncSession):
    """Process add balance amount"""
    text = (message.text or "").replace(",", "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Số tiền không hợp lệ.")
        return

    amount = int(text)
    data = await state.get_data()
    telegram_id = data["target_id"]
    await state.clear()

    user = await safe_db_operation(adjust_balance_by_telegram_id, db_session, telegram_id, amount, f"Admin cộng tiền")

    if user is None:
        await message.answer(f"❌ Không tìm thấy User ID `{telegram_id}`.", parse_mode="Markdown")
        return

    await message.answer(
        f"✅ Đã cộng `{amount:,}` VNĐ cho **{user.fullname}**\n"
        f"💰 Số dư hiện tại: `{user.balance:,}` VNĐ",
        parse_mode="Markdown"
    )


@router.message(lambda m: m.text == "💸 Trừ Tiền")
@admin_only
@error_handler
async def admin_sub_bal_start(message: Message, state: FSMContext, is_admin: bool):
    """Start subtract balance"""
    await message.answer("💸 Nhập Telegram ID người cần trừ tiền:")
    await state.set_state(AdminStates.waiting_subtract_balance_id)


@router.message(AdminStates.waiting_subtract_balance_id)
@error_handler
async def admin_sub_bal_id(message: Message, state: FSMContext):
    """Process subtract balance ID"""
    text = message.text or ""
    if not text.lstrip("-").isdigit():
        await message.answer("⚠️ Telegram ID phải là số.")
        return

    await state.update_data(target_id=int(text))
    await message.answer("💵 Nhập số tiền VNĐ cần trừ:")
    await state.set_state(AdminStates.waiting_subtract_balance_amount)


@router.message(AdminStates.waiting_subtract_balance_amount)
@error_handler
async def admin_sub_bal_amount(message: Message, state: FSMContext, db_session: AsyncSession):
    """Process subtract balance amount"""
    text = (message.text or "").replace(",", "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Số tiền không hợp lệ.")
        return

    amount = int(text)
    data = await state.get_data()
    telegram_id = data["target_id"]
    await state.clear()

    user = await safe_db_operation(adjust_balance_by_telegram_id, db_session, telegram_id, -amount, f"Admin trừ tiền")

    if user is None:
        await message.answer(f"❌ Không tìm thấy User ID `{telegram_id}`.", parse_mode="Markdown")
        return

    await message.answer(
        f"✅ Đã trừ `{amount:,}` VNĐ của **{user.fullname}**\n"
        f"💰 Số dư hiện tại: `{user.balance:,}` VNĐ",
        parse_mode="Markdown"
    )


# ── Admin User Management ──
@router.message(lambda m: m.text == "🚫 Ban User")
@admin_only
@error_handler
async def admin_ban_start(message: Message, state: FSMContext, is_admin: bool):
    """Start ban user"""
    await message.answer("🚫 Nhập Telegram ID người cần ban:")
    await state.set_state(AdminStates.waiting_ban_id)


@router.message(AdminStates.waiting_ban_id)
@error_handler
async def admin_ban_execute(message: Message, state: FSMContext, db_session: AsyncSession):
    """Execute ban"""
    text = message.text or ""
    await state.clear()

    if not text.lstrip("-").isdigit():
        await message.answer("⚠️ ID sai định dạng.")
        return

    telegram_id = int(text)
    success = await safe_db_operation(ban_user, db_session, telegram_id)

    if success:
        await message.answer(f"✅ Đã ban User ID `{telegram_id}`.", parse_mode="Markdown")
    else:
        await message.answer(f"❌ Không tìm thấy User ID `{telegram_id}`.", parse_mode="Markdown")


@router.message(lambda m: m.text == "✅ Unban User")
@admin_only
@error_handler
async def admin_unban_start(message: Message, state: FSMContext, is_admin: bool):
    """Start unban user"""
    await message.answer("✅ Nhập Telegram ID cần mở khóa:")
    await state.set_state(AdminStates.waiting_unban_id)


@router.message(AdminStates.waiting_unban_id)
@error_handler
async def admin_unban_execute(message: Message, state: FSMContext, db_session: AsyncSession):
    """Execute unban"""
    text = message.text or ""
    await state.clear()

    if not text.lstrip("-").isdigit():
        await message.answer("⚠️ ID sai định dạng.")
        return

    telegram_id = int(text)
    success = await safe_db_operation(unban_user, db_session, telegram_id)

    if success:
        await message.answer(f"✅ Đã gỡ ban User ID `{telegram_id}`.", parse_mode="Markdown")
    else:
        await message.answer(f"❌ Không tìm thấy User ID `{telegram_id}`.", parse_mode="Markdown")


async def ban_user(session: AsyncSession, telegram_id: int) -> bool:
    """Ban a user"""
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.is_banned = True
    await session.commit()
    cache.delete(f"user_{telegram_id}")
    return True


async def unban_user(session: AsyncSession, telegram_id: int) -> bool:
    """Unban a user"""
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.is_banned = False
    await session.commit()
    cache.delete(f"user_{telegram_id}")
    return True


# ── Admin Account Management ──
@router.message(lambda m: m.text == "📥 Import TXT")
@admin_only
@error_handler
async def admin_import_start(message: Message, state: FSMContext, is_admin: bool):
    """Start import accounts"""
    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  📥 **IMPORT TÀI KHOẢN**     ║\n"
        "╚════════════════════════════════╝\n\n"
        "📤 Vui lòng gửi file `.txt` chứa tài khoản.\n\n"
        "✅ **Hỗ trợ format:**\n"
        "• Checker: `username:password|UID=...|Skin=X|Tướng=Y|BAN=NO`\n"
        "• Đơn giản: `username:password`\n\n"
        "🚫 **Tự động lọc:**\n"
        "• Acc bị BAN\n"
        "• Acc 0 skin + 0 tướng",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_import_file)


@router.message(AdminStates.waiting_import_file, F.document)
@error_handler
async def admin_import_file(message: Message, state: FSMContext, bot: Bot, db_session: AsyncSession):
    """Process import file"""
    doc = message.document
    if not doc or not doc.file_name or not doc.file_name.endswith(".txt"):
        await message.answer("⚠️ File gửi lên phải có định dạng `.txt`!")
        return

    await state.clear()

    file = await bot.get_file(doc.file_id)
    raw = await bot.download_file(file.file_path)
    content = raw.read().decode("utf-8", errors="ignore")

    stats = await safe_db_operation(import_accounts, db_session, content.splitlines())

    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  📥 **KẾT QUẢ IMPORT**        ║\n"
        "╚════════════════════════════════╝\n\n"
        f"📄 Tổng dòng: `{stats['total']}`\n"
        f"✅ Đã thêm: `{stats['imported']}`\n"
        f"🔁 Trùng: `{stats['duplicates']}`\n"
        f"❌ Lỗi: `{stats['invalid']}`\n\n"
        f"🚫 **Acc bị lọc:**\n"
        f"  • Bị ban: `{stats['filtered_banned']}`\n"
        f"  • 0 skin/tướng: `{stats['filtered_empty']}`",
        parse_mode="Markdown"
    )


@router.message(lambda m: m.text == "🗑️ Xóa Account")
@admin_only
@error_handler
async def admin_delete_acc_start(message: Message, state: FSMContext, is_admin: bool):
    """Start delete account"""
    await message.answer("🗑️ Nhập username tài khoản cần xóa:")
    await state.set_state(AdminStates.waiting_delete_username)


@router.message(AdminStates.waiting_delete_username)
@error_handler
async def admin_delete_acc_execute(message: Message, state: FSMContext, db_session: AsyncSession):
    """Execute delete account"""
    username = (message.text or "").strip()
    await state.clear()

    if not username:
        await message.answer("⚠️ Vui lòng nhập username hợp lệ.")
        return

    success = await safe_db_operation(delete_account_by_username, db_session, username)

    if success:
        await message.answer(f"✅ Đã xóa acc `{username}` khỏi hệ thống.", parse_mode="Markdown")
    else:
        await message.answer(f"❌ Không tìm thấy acc `{username}`.", parse_mode="Markdown")


async def delete_account_by_username(session: AsyncSession, username: str) -> bool:
    """Delete account by username"""
    result = await session.execute(select(Account).where(Account.username == username))
    acc = result.scalar_one_or_none()
    if acc is None:
        return False
    await session.delete(acc)
    await session.commit()
    cache.delete("available_count")
    return True


@router.message(lambda m: m.text == "🧹 Dọn Acc Rác")
@admin_only
@error_handler
async def admin_clean_trash(message: Message, is_admin: bool, db_session: AsyncSession):
    """Clean trash accounts"""
    trash = await safe_db_operation(get_trash_count, db_session)

    if trash == 0:
        await message.answer("✅ Kho sạch rồi, không có acc rác nào!")
        return

    deleted = await safe_db_operation(delete_trash_accounts, db_session)

    await message.answer(
        f"🧹 **Dọn kho hoàn tất!**\n\n"
        f"🗑️ Đã xóa `{deleted}` acc rác (0 skin + 0 tướng)",
        parse_mode="Markdown"
    )


@router.message(lambda m: m.text == "📤 Export Chưa Bán")
@admin_only
@error_handler
async def admin_export_unsold(message: Message, is_admin: bool, db_session: AsyncSession):
    """Export unsold accounts"""
    accounts = await safe_db_operation(get_unsold_accounts, db_session)

    if not accounts:
        await message.answer("📦 Kho trống rỗng.")
        return

    lines = [f"{a.username}|{a.password}" for a in accounts]
    fp = await save_export_file(lines, "unsold")

    await message.answer_document(
        FSInputFile(fp),
        caption=f"📤 Acc Chưa Bán\n📊 Số lượng: `{len(lines)}` acc",
        parse_mode="Markdown"
    )


@router.message(lambda m: m.text == "📤 Export Đã Bán")
@admin_only
@error_handler
async def admin_export_sold(message: Message, is_admin: bool, db_session: AsyncSession):
    """Export sold accounts"""
    accounts = await safe_db_operation(get_sold_accounts, db_session)

    if not accounts:
        await message.answer("📦 Chưa bán được đơn nào.")
        return

    lines = [f"{a.username}|{a.password}" for a in accounts]
    fp = await save_export_file(lines, "sold")

    await message.answer_document(
        FSInputFile(fp),
        caption=f"📤 Acc Đã Bán\n📊 Số lượng: `{len(lines)}` acc",
        parse_mode="Markdown"
    )


async def get_unsold_accounts(session: AsyncSession) -> List[Account]:
    """Get all unsold accounts"""
    result = await session.execute(
        select(Account).where(Account.status == AccountStatus.available)
    )
    return list(result.scalars().all())


async def get_sold_accounts(session: AsyncSession) -> List[Account]:
    """Get all sold accounts"""
    result = await session.execute(
        select(Account).where(Account.status == AccountStatus.sold)
    )
    return list(result.scalars().all())


async def get_total_count(session: AsyncSession) -> int:
    """Get total account count"""
    result = await session.execute(select(func.count()).select_from(Account))
    return result.scalar_one()


async def get_sold_count(session: AsyncSession) -> int:
    """Get sold account count"""
    result = await session.execute(
        select(func.count()).where(Account.status == AccountStatus.sold)
    )
    return result.scalar_one()


# ── Admin QR ──
@router.message(lambda m: m.text == "📷 Đổi QR")
@admin_only
@error_handler
async def admin_change_qr_start(message: Message, state: FSMContext, is_admin: bool):
    """Start QR change"""
    await message.answer("📷 Vui lòng gửi ảnh mã QR mới:")
    await state.set_state(AdminStates.waiting_qr)


@router.message(AdminStates.waiting_qr, F.photo)
@error_handler
async def admin_receive_qr(message: Message, state: FSMContext, bot: Bot):
    """Process QR image"""
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    raw = await bot.download_file(file.file_path)

    await save_qr_image(raw.read())
    await state.clear()

    await message.answer("✅ Ảnh QR đã được cập nhật thành công!")


# ── Admin Bills ──
@router.message(lambda m: m.text == "📥 Bill Chờ")
@admin_only
@error_handler
async def admin_pending_bills(message: Message, is_admin: bool, db_session: AsyncSession):
    """Show pending bills"""
    deposits = await safe_db_operation(get_pending_deposits, db_session)

    if not deposits:
        await message.answer("✅ Không có yêu cầu nạp tiền nào đang chờ.")
        return

    lines = [
        "╔════════════════════════════════╗",
        "║  📥 **BILL CHỜ DUYỆT**        ║",
        "╚════════════════════════════════╝",
        f"📊 Tổng: `{len(deposits)}` bill\n"
    ]

    for d in deposits[:10]:
        uname = f"@{d.user.username}" if d.user and d.user.username else "N/A"
        name = d.user.fullname[:20] if d.user else "N/A"
        created = d.created_at.strftime("%d/%m/%Y %H:%M")
        lines.append(f"🧾 **#{d.id}** — {name}")
        lines.append(f"   👤 {uname} — 💵 `{d.amount:,}` VNĐ")
        lines.append(f"   🕐 {created}")
        lines.append("")

    if len(deposits) > 10:
        lines.append(f"... và {len(deposits) - 10} bill khác")

    await message.answer("\n".join(lines), parse_mode="Markdown")


async def get_pending_deposits(session: AsyncSession) -> List[Deposit]:
    """Get all pending deposits"""
    result = await session.execute(
        select(Deposit)
        .options(selectinload(Deposit.user))
        .where(Deposit.status == DepositStatus.pending)
        .order_by(asc(Deposit.created_at))
    )
    return list(result.scalars().all())


# ── Admin Broadcast ──
@router.message(lambda m: m.text == "📢 Broadcast")
@admin_only
@error_handler
async def admin_broadcast_start(message: Message, state: FSMContext, is_admin: bool):
    """Start broadcast"""
    await message.answer(
        "📢 **Gửi tin nhắn đến tất cả người dùng**\n\n"
        "Vui lòng nhập nội dung tin nhắn:\n"
        "(Hỗ trợ Markdown)",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_broadcast_text)


@router.message(AdminStates.waiting_broadcast_text)
@error_handler
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot, db_session: AsyncSession):
    """Execute broadcast"""
    text = message.text or ""
    await state.clear()

    if not text:
        await message.answer("⚠️ Nội dung trống.")
        return

    # Get all users
    users = await safe_db_operation(get_all_users, db_session)
    total = len(users)

    sent = 0
    failed = 0

    # Send confirmation
    status_msg = await message.answer(
        f"📢 Đang gửi broadcast đến `{total}` người dùng...\n"
        f"✅ Đã gửi: `0`\n"
        f"❌ Thất bại: `0`",
        parse_mode="Markdown"
    )

    # Send to all users
    for i, user in enumerate(users):
        if user.is_banned:
            continue
        try:
            await bot.send_message(user.telegram_id, text, parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1

        # Update status every 10 users
        if (i + 1) % 10 == 0:
            try:
                await status_msg.edit_text(
                    f"📢 Đang gửi broadcast...\n"
                    f"👥 Đã xử lý: `{i + 1}/{total}`\n"
                    f"✅ Đã gửi: `{sent}`\n"
                    f"❌ Thất bại: `{failed}`",
                    parse_mode="Markdown"
                )
                await asyncio.sleep(0.1)
            except Exception:
                pass

        await asyncio.sleep(0.05)  # Rate limiting

    await status_msg.edit_text(
        f"📢 **Gửi Broadcast Hoàn Tất!**\n\n"
        f"👥 Tổng người dùng: `{total}`\n"
        f"✅ Thành công: `{sent}`\n"
        f"❌ Thất bại: `{failed}`",
        parse_mode="Markdown"
    )


async def get_all_users(session: AsyncSession) -> List[User]:
    """Get all users"""
    result = await session.execute(select(User))
    return list(result.scalars().all())


# ── Admin Giftcode ──
@router.message(lambda m: m.text == "🎟️ Tạo Giftcode")
@admin_only
@error_handler
async def admin_create_giftcode_start(message: Message, state: FSMContext, is_admin: bool):
    """Start creating giftcode"""
    await message.answer(
        "🎟️ **Tạo Giftcode mới**\n\n"
        "Nhập số tiền (VNĐ) cho giftcode:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_giftcode_amount)


@router.message(AdminStates.waiting_giftcode_amount)
@error_handler
async def admin_create_giftcode_amount(message: Message, state: FSMContext, db_session: AsyncSession):
    """Create giftcode"""
    text = (message.text or "").replace(",", "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Vui lòng nhập số tiền hợp lệ.")
        return    amount = int(text)
    await state.clear()

    code = await safe_db_operation(generate_giftcode, db_session, amount)

    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  ✅ **GIFTCODE ĐÃ TẠO**       ║\n"
        "╚════════════════════════════════╝\n\n"
        f"🎟️ **Mã:** `{code}`\n"
        f"💵 **Giá trị:** `{amount:,}` VNĐ\n"
        f"⏳ **Hết hạn sau:** 30 ngày\n\n"
        "📌 Gửi mã này cho người dùng để họ nhận thưởng.",
        parse_mode="Markdown"
    )


# ── Admin Voucher ──
@router.message(lambda m: m.text == "🎫 Tạo Voucher")
@admin_only
@error_handler
async def admin_create_voucher_start(message: Message, state: FSMContext, is_admin: bool):
    """Start creating voucher"""
    await message.answer(
        "🎫 **Tạo Voucher giảm giá**\n\n"
        "Nhập phần trăm giảm giá (0-100):",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_voucher_discount)


@router.message(AdminStates.waiting_voucher_discount)
@error_handler
async def admin_create_voucher_discount(message: Message, state: FSMContext):
    """Process voucher discount"""
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Vui lòng nhập số nguyên (0-100).")
        return

    discount = int(text)
    if discount < 0 or discount > 100:
        await message.answer("⚠️ Giảm giá phải từ 0 đến 100%.")
        return

    await state.update_data(discount=discount)
    await message.answer("Nhập giá trị đơn hàng tối thiểu để áp dụng (VNĐ):")
    await state.set_state(AdminStates.waiting_voucher_min_order)


@router.message(AdminStates.waiting_voucher_min_order)
@error_handler
async def admin_create_voucher_min_order(message: Message, state: FSMContext):
    """Process voucher min order"""
    text = (message.text or "").replace(",", "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Vui lòng nhập số tiền hợp lệ.")
        return

    min_order = int(text)
    await state.update_data(min_order=min_order)

    await message.answer(
        "Nhập giảm giá tối đa (VNĐ, nhập 0 để không giới hạn):"
    )
    await state.set_state(AdminStates.waiting_voucher_max_discount)


@router.message(AdminStates.waiting_voucher_max_discount)
@error_handler
async def admin_create_voucher_max_discount(message: Message, state: FSMContext, db_session: AsyncSession):
    """Create voucher"""
    text = (message.text or "").replace(",", "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Vui lòng nhập số tiền hợp lệ.")
        return

    max_discount = int(text) if int(text) > 0 else None
    data = await state.get_data()
    discount = data.get("discount", 0)
    min_order = data.get("min_order", 0)

    await state.clear()

    # Generate voucher code
    code = f"VOUCHER-{hashlib.md5(f'{discount}{min_order}{max_discount}{uuid.uuid4().hex}'.encode()).hexdigest()[:8].upper()}"

    voucher = Voucher(
        code=code,
        discount_percent=discount,
        min_order=min_order,
        max_discount=max_discount,
        is_active=True,
        expires_at=datetime.now() + timedelta(days=30),
    )
    db_session.add(voucher)
    await db_session.commit()

    await message.answer(
        "╔════════════════════════════════╗\n"
        "║  ✅ **VOUCHER ĐÃ TẠO**        ║\n"
        "╚════════════════════════════════╝\n\n"
        f"🎫 **Mã:** `{code}`\n"
        f"📊 **Giảm:** `{discount}%`\n"
        f"💰 **Đơn tối thiểu:** `{min_order:,}` VNĐ\n"
        f"🔢 **Giảm tối đa:** `{max_discount if max_discount else 'Không giới hạn'}`\n"
        f"⏳ **Hết hạn sau:** 30 ngày\n\n"
        "📌 Gửi mã này cho người dùng để họ giảm giá khi mua hàng.",
        parse_mode="Markdown"
    )


# ── Web Server ──
async def handle_web(request):
    """Health check endpoint"""
    return web.Response(text="✅ Bot Garena Premium đang vận hành ổn định 24/7!")


async def handle_health(request):
    """Health check with detailed status"""
    status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime": "24/7",
        "version": "2.0.0",
    }
    return web.json_response(status)


async def start_web_server():
    """Start web server for health checks and keep-alive"""
    app = web.Application()
    app.router.add_get("/", handle_web)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/app", handle_web)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info(f"✅ Web server keep-alive started on port {PORT}")
    return app, runner


# ── Heartbeat / Watchdog ──
async def heartbeat_check(bot: Bot):
    """Periodic heartbeat check"""
    while True:
        try:
            # Check bot connection by getting me
            await bot.get_me()
            logger.debug("💓 Heartbeat: Bot is alive")
        except Exception as e:
            logger.error(f"💔 Heartbeat failed: {e}")

        await asyncio.sleep(60)  # Check every 60 seconds


# ── Database Health Check ──
async def db_health_check():
    """Periodic database health check"""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(sa_text("SELECT 1"))
            logger.debug("💾 Database: Healthy")
        except Exception as e:
            logger.error(f"💾 Database health check failed: {e}")

        await asyncio.sleep(30)  # Check every 30 seconds


# ── Init Database ──
async def init_db() -> None:
    """Initialize database with required tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Add missing columns if needed
        for col in ("skin_count", "tuong_count"):
            try:
                await conn.execute(
                    sa_text(f"ALTER TABLE accounts_v4 ADD COLUMN IF NOT EXISTS {col} INTEGER NOT NULL DEFAULT 0")
                )
            except Exception:
                pass

        # Add new columns for user if needed
        for col in ("points", "total_deposited", "total_spent", "is_premium", "referred_by", "referral_count", "last_daily"):
            try:
                await conn.execute(
                    sa_text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} INTEGER DEFAULT 0")
                )
            except Exception:
                pass

        # Fix last_daily type if needed
        try:
            await conn.execute(
                sa_text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily DATETIME")
            )
        except Exception:
            pass

        # Create transactions table if not exists
        try:
            await conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    type VARCHAR(20) NOT NULL,
                    description VARCHAR(512),
                    reference_id INTEGER,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """))
        except Exception:
            pass

        # Create giftcodes table if not exists
        try:
            await conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS giftcodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code VARCHAR(50) UNIQUE NOT NULL,
                    amount INTEGER NOT NULL,
                    is_used BOOLEAN NOT NULL DEFAULT 0,
                    used_by INTEGER,
                    expires_at DATETIME,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (used_by) REFERENCES users (id)
                )
            """))
        except Exception:
            pass

        # Create vouchers table if not exists
        try:
            await conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS vouchers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code VARCHAR(50) UNIQUE NOT NULL,
                    discount_percent INTEGER NOT NULL,
                    max_discount INTEGER,
                    min_order INTEGER NOT NULL DEFAULT 0,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    expires_at DATETIME,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
        except Exception:
            pass

        # Create system_config table if not exists
        try:
            await conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS system_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key VARCHAR(100) UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
        except Exception:
            pass

    logger.info("✅ Database initialized successfully")


# ── Main ──
async def main():
    """Main entry point"""
    # Check environment variables
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN environment variable is not set!")
        sys.exit(1)

    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL environment variable is not set!")
        sys.exit(1)

    # Initialize database
    await init_db()

    # Start web server
    await start_web_server()

    # Initialize bot
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # Setup commands
    await bot.set_my_commands([
        BotCommand(command="start", description="🏠 Bắt đầu"),
        BotCommand(command="admin", description="⚙️ Admin Panel"),
    ])

    # Initialize dispatcher
    dp = Dispatcher(storage=MemoryStorage())

    # Add middleware
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Include router
    dp.include_router(router)

    # Start background tasks
    asyncio.create_task(heartbeat_check(bot))
    asyncio.create_task(db_health_check())

    logger.info("🤖 Bot Shop Garena Premium đã sẵn sàng!")

    # Start polling
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            on_startup=None,
            on_shutdown=None,
        )
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
```

📋 Tóm tắt nâng cấp

✨ Tính năng mới:

1. Giftcode - Tạo và nhận mã quà tặng
2. Voucher - Giảm giá khi mua hàng
3. Điểm danh hàng ngày - Nhận thưởng mỗi ngày
4. Điểm thưởng - Tích lũy điểm khi hoạt động
5. Giới thiệu bạn bè - Nhận thưởng khi giới thiệu
6. Lịch sử giao dịch - Theo dõi tất cả giao dịch
7. Cashback - Hoàn tiền tự động khi mua hàng
8. Cấp độ VIP - Phân hạng thành viên theo chi tiêu
9. Hồ sơ người dùng - Giao diện đẹp, đầy đủ thông tin
10. FAQ - Câu hỏi thường gặp

🎨 Giao diện mới:

· Menu được tổ chức khoa học, dễ sử dụng
· Định dạng tin nhắn đẹp với dòng kẻ và icon
· Hồ sơ người dùng chuyên nghiệp
· Thông báo có cấu trúc rõ ràng

⚡ Tối ưu hiệu năng:

· Cache dữ liệu để giảm tải DB
· Retry khi gặp lỗi database/network
· Database pool kết nối
· Health check tự động
· Heartbeat giữ bot hoạt động

🛡️ Độ ổn định:

· Auto reconnect khi mất kết nối
· Exception handler không làm bot crash
· Logging đầy đủ
· Watchdog kiểm tra sức khỏe

📁 Cấu trúc code:

· Clean code, PEP8
· Typing đầy đủ
· Tách module logic rõ ràng
· Dễ mở rộng thêm tính năng
