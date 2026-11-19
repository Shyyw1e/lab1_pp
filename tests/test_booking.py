import copy
from decimal import Decimal
from datetime import datetime
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from booking.models import Booking, BookingError, BookingStatus, Customer, Event, StorageError, Venue
from booking.service import BookingSystem
from booking.storage import JsonStorage, XmlStorage, from_data, to_data
from main import run, select_item
from dataclasses import FrozenInstanceError
from uuid import UUID


def example():
    system = BookingSystem()
    venue = Venue('Концертный зал', 'ул. Мира, 1', 3)
    system.add_venue(venue)
    system.add_event(Event('Джазовый вечер', venue.id,
                           datetime(2027, 5, 20, 19), Decimal('1250.50')))
    system.add_customer(Customer('Анна', 'anna@example.org'))
    return system


class BookingTests(unittest.TestCase):
    def setUp(self):
        self.system = example()
        self.venue_id = next(iter(self.system.venues))
        self.event_id = next(iter(self.system.events))
        self.customer_id = next(iter(self.system.customers))

    def test_generated_ids_cannot_be_supplied_or_changed(self):
        booking = self.system.book(self.event_id, self.customer_id, 1)
        objects = [*self.system.venues.values(), *self.system.events.values(),
                   *self.system.customers.values(), booking]
        for item in objects:
            self.assertEqual(UUID(item.id).version, 4)
            with self.assertRaises(FrozenInstanceError):
                item.id = 'custom-id'
        self.assertEqual(len({item.id for item in objects}), len(objects))
        cases = [(Venue, dict(name='Зал', address='Адрес', capacity=3)),
                 (Customer, dict(name='Имя', email='name@example.org')),
                 (Event, dict(title='Тест', venue_id=self.venue_id,
                              starts_at=datetime(2027, 1, 1), price=Decimal('1'))),
                 (Booking, dict(event_id=self.event_id, customer_id=self.customer_id,
                                quantity=1, unit_price=Decimal('1')))]
        for model, kwargs in cases:
            with self.subTest(model=model.__name__), self.assertRaises(TypeError):
                model(id='custom-id', **kwargs)
        self.assertNotEqual(Customer('Имя', 'name@example.org').id,
                            Customer('Имя', 'name@example.org').id)

    def test_cancel_preserves_id(self):
        booking = self.system.book(self.event_id, self.customer_id, 1)
        self.system.cancel(booking.id)
        self.assertEqual(self.system.bookings[booking.id].id, booking.id)

    def test_selection_rejects_out_of_range(self):
        for answer in ('0', '-1', '2', 'custom-id'):
            with patch('builtins.input', return_value=answer), patch('sys.stdout', new_callable=io.StringIO):
                with self.assertRaises(ValueError):
                    select_item(self.system.venues, lambda v: v.name)

    def test_cli_creates_and_links_without_id_input(self):
        answers = iter(['1', 'Зал', 'Адрес', '3', '2', '1', 'Концерт',
                        '2027-05-20T19:00', '100.00', '3', 'Анна', 'anna@example.org',
                        '5', '1', '1', '2', '6', '1', '7', '0'])
        prompts = []
        def respond(prompt):
            prompts.append(prompt)
            return next(answers)
        with patch('builtins.input', side_effect=respond), patch('sys.stdout', new_callable=io.StringIO) as output:
            run()
        self.assertNotIn('Ошибка:', output.getvalue())
        self.assertIn('200.00', output.getvalue())
        self.assertIn('cancelled', output.getvalue())
        self.assertFalse(any('ID' in prompt for prompt in prompts))

    def test_booking_and_total(self):
        booking = self.system.book(self.event_id, self.customer_id, 2)
        self.assertEqual(booking.total, Decimal('2501.00'))
        self.assertEqual(self.system.available_seats(self.event_id), 1)

    def test_overbooking_is_atomic(self):
        self.system.book(self.event_id, self.customer_id, 2)
        before = to_data(self.system)
        with self.assertRaises(BookingError):
            self.system.book(self.event_id, self.customer_id, 2)
        self.assertEqual(to_data(self.system), before)

    def test_cancel_releases_seats(self):
        booking = self.system.book(self.event_id, self.customer_id, 3)
        self.system.cancel(booking.id)
        self.assertEqual(self.system.available_seats(self.event_id), 3)
        self.assertEqual(self.system.bookings[booking.id].status, BookingStatus.CANCELLED)
        with self.assertRaises(BookingError):
            self.system.cancel(booking.id)

    def test_invalid_quantity(self):
        for quantity in (0, -1, True, 1.5):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.system.book(self.event_id, self.customer_id, quantity)

    def test_unknown_references(self):
        for event, customer in (('missing', self.customer_id), (self.event_id, 'missing')):
            with self.assertRaises(BookingError):
                self.system.book(event, customer, 1)
        self.assertEqual(len(self.system.bookings), 0)
        with self.assertRaises(BookingError):
            self.system.add_event(Event('Тест', 'missing', datetime(2027, 1, 1), Decimal('0')))

    def test_duplicate_ids(self):
        with self.assertRaises(BookingError):
            self.system.add_customer(self.system.customers[self.customer_id])

    def test_invalid_models(self):
        for price in ('-1', 'NaN', 'Infinity', '1.001'):
            with self.subTest(price=price), self.assertRaises(ValueError):
                Event('Тест', self.venue_id, datetime(2027, 1, 1), Decimal(price))
        with self.assertRaises(ValueError):
            Customer('Имя', 'bad-email')
        with self.assertRaises(ValueError):
            Venue('Зал', 'Адрес', 0)

    def test_public_collections_readonly(self):
        with self.assertRaises(TypeError):
            self.system.events['bad'] = self.system.events[self.event_id]

    def test_roundtrip_both_formats(self):
        cancelled = self.system.book(self.event_id, self.customer_id, 3)
        self.system.cancel(cancelled.id)
        self.system.book(self.event_id, self.customer_id, 2)
        with TemporaryDirectory() as directory:
            for storage in (JsonStorage(), XmlStorage()):
                with self.subTest(storage=type(storage).__name__):
                    path = Path(directory) / 'data'
                    storage.save(self.system, path)
                    restored = storage.load(path)
                    self.assertEqual(to_data(restored), to_data(self.system))
                    self.assertEqual(restored.available_seats(self.event_id), 1)

    def test_corrupt_files_and_missing_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'data'
            for storage in (JsonStorage(), XmlStorage()):
                with self.assertRaises(StorageError):
                    storage.load(path)
                path.write_text('broken', encoding='utf-8')
                with self.assertRaises(StorageError):
                    storage.load(path)
                path.unlink()
                with self.assertRaises(StorageError):
                    storage.save(self.system, Path(directory) / 'missing' / 'data')

    def test_semantically_invalid_files(self):
        self.system.book(self.event_id, self.customer_id, 1)
        original = to_data(self.system)
        mutations = [
            lambda d: d.update(version=2),
            lambda d: d['venues'][0].update(id='custom-id'),
            lambda d: d['events'][0].update(venue_id='missing'),
            lambda d: d['bookings'][0].update(quantity=4),
            lambda d: d['bookings'][0].update(status='unknown'),
            lambda d: d['customers'].append(d['customers'][0].copy()),
            lambda d: d['events'][0].update(price='NaN'),
            lambda d: d['venues'][0].update(capacity=True),
        ]
        with TemporaryDirectory() as directory:
            for mutation in mutations:
                data = copy.deepcopy(original)
                mutation(data)
                for storage in (JsonStorage(), XmlStorage()):
                    path = Path(directory) / 'bad'
                    path.write_text(storage.encode(data), encoding='utf-8')
                    with self.subTest(data=data, storage=type(storage).__name__), self.assertRaises(StorageError):
                        storage.load(path)
        self.assertEqual(to_data(self.system), original)

    def test_duplicate_json_fields(self):
        with self.assertRaises(ValueError):
            JsonStorage().decode('{"version":1,"version":2}')

    def test_cli_continues_after_error(self):
        answers = iter(['invalid', '1', 'Зал', 'Адрес', 'not-a-number', '0'])
        with patch('builtins.input', side_effect=lambda _: next(answers)), patch('sys.stdout', new_callable=io.StringIO) as output:
            run()
        self.assertEqual(output.getvalue().count('Ошибка:'), 2)

    def test_cli_keeps_state_after_failed_load(self):
        answers = iter(['9', 'json', 'data/example.json', '9', 'json',
                        '/no/such/booking/file.json', '4', '0'])
        with patch('builtins.input', side_effect=lambda _: next(answers)), patch('sys.stdout', new_callable=io.StringIO) as output:
            run()
        self.assertIn('Джазовый вечер', output.getvalue())
        self.assertIn('Ошибка:', output.getvalue())


if __name__ == '__main__':
    unittest.main()
