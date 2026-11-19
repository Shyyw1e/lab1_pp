"""Объекты предметной области. Денежные значения хранятся точно в Decimal."""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4


class BookingError(Exception):
    """Нарушение правил бронирования."""


class StorageError(Exception):
    """Ошибка чтения, записи или структуры файла."""


def text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: требуется непустая строка")


def positive(value: int, field: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field}: требуется положительное целое число")


@dataclass(frozen=True)
class Venue:
    id: str = field(default_factory=lambda: str(uuid4()), init=False)
    name: str
    address: str
    capacity: int

    def __post_init__(self):
        for field in ('id', 'name', 'address'):
            text(getattr(self, field), field)
        positive(self.capacity, 'Вместимость')


@dataclass(frozen=True)
class Event:
    id: str = field(default_factory=lambda: str(uuid4()), init=False)
    title: str
    venue_id: str
    starts_at: datetime
    price: Decimal

    def __post_init__(self):
        for field in ('id', 'title', 'venue_id'):
            text(getattr(self, field), field)
        if not isinstance(self.starts_at, datetime):
            raise ValueError('Требуется дата мероприятия')
        if (not isinstance(self.price, Decimal) or not self.price.is_finite()
                or self.price < 0 or self.price.as_tuple().exponent < -2):
            raise ValueError('Цена должна быть неотрицательной, с точностью до копеек')


@dataclass(frozen=True)
class Customer:
    id: str = field(default_factory=lambda: str(uuid4()), init=False)
    name: str
    email: str

    def __post_init__(self):
        for field in ('id', 'name', 'email'):
            text(getattr(self, field), field)
        if self.email.count('@') != 1 or any(c.isspace() for c in self.email):
            raise ValueError('Некорректный email')
        local, domain = self.email.split('@')
        if not local or '.' not in domain or any(not s for s in domain.split('.')):
            raise ValueError('Некорректный email')


class BookingStatus(str, Enum):
    ACTIVE = 'active'
    CANCELLED = 'cancelled'


@dataclass(frozen=True)
class Booking:
    id: str = field(default_factory=lambda: str(uuid4()), init=False)
    event_id: str
    customer_id: str
    quantity: int
    unit_price: Decimal
    status: BookingStatus = BookingStatus.ACTIVE

    def __post_init__(self):
        for field in ('id', 'event_id', 'customer_id'):
            text(getattr(self, field), field)
        positive(self.quantity, 'Количество билетов')
        if (not isinstance(self.unit_price, Decimal) or not self.unit_price.is_finite()
                or self.unit_price < 0 or self.unit_price.as_tuple().exponent < -2):
            raise ValueError('Некорректная цена билета')
        if not isinstance(self.status, BookingStatus):
            raise ValueError('Некорректный статус')

    @property
    def total(self) -> Decimal:
        return self.unit_price * self.quantity
