"""Операции системы и проверка целостности связей."""
from dataclasses import replace
from types import MappingProxyType

from .models import Booking, BookingError, BookingStatus, Customer, Event, Venue, positive


class BookingSystem:
    def __init__(self):
        self._venues = {}
        self._events = {}
        self._customers = {}
        self._bookings = {}

    @property
    def venues(self):
        return MappingProxyType(self._venues)

    @property
    def events(self):
        return MappingProxyType(self._events)

    @property
    def customers(self):
        return MappingProxyType(self._customers)

    @property
    def bookings(self):
        return MappingProxyType(self._bookings)

    @staticmethod
    def _add(collection, item):
        if item.id in collection:
            raise BookingError(f'Идентификатор уже существует: {item.id}')
        collection[item.id] = item

    @staticmethod
    def _get(collection, identifier):
        try:
            return collection[identifier]
        except KeyError as exc:
            raise BookingError(f'Объект не найден: {identifier}') from exc

    def add_venue(self, venue: Venue):
        self._add(self._venues, venue)

    def add_event(self, event: Event):
        self._get(self._venues, event.venue_id)
        self._add(self._events, event)

    def add_customer(self, customer: Customer):
        self._add(self._customers, customer)

    def available_seats(self, event_id: str) -> int:
        event = self._get(self._events, event_id)
        occupied = sum(b.quantity for b in self._bookings.values()
                       if b.event_id == event_id and b.status == BookingStatus.ACTIVE)
        return self._venues[event.venue_id].capacity - occupied

    def restore_booking(self, booking: Booking):
        """Восстановление записи с проверкой ссылок и вместимости."""
        self._get(self._events, booking.event_id)
        self._get(self._customers, booking.customer_id)
        if (booking.status == BookingStatus.ACTIVE
                and booking.quantity > self.available_seats(booking.event_id)):
            raise BookingError('Недостаточно свободных мест')
        self._add(self._bookings, booking)

    def book(self, event_id: str, customer_id: str, quantity: int) -> Booking:
        positive(quantity, 'Количество билетов')
        event = self._get(self._events, event_id)
        booking = Booking(event_id, customer_id, quantity, event.price)
        self.restore_booking(booking)
        return booking

    def cancel(self, booking_id: str):
        booking = self._get(self._bookings, booking_id)
        if booking.status == BookingStatus.CANCELLED:
            raise BookingError('Бронирование уже отменено')
        cancelled = replace(booking, status=BookingStatus.CANCELLED)
        object.__setattr__(cancelled, 'id', booking.id)
        self._bookings[booking_id] = cancelled
