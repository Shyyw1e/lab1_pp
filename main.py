"""Запуск: python3 main.py. Все команды выполняются в цикле с обработкой ошибок."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from booking.models import BookingError, Customer, Event, StorageError, Venue
from booking.service import BookingSystem
from booking.storage import JsonStorage, XmlStorage


def select_item(collection, label):
    """Пользователь выбирает существующий объект, а не задаёт его UUID."""
    items = list(collection.values())
    if not items:
        raise BookingError('Список пуст: сначала создайте необходимые объекты')
    for index, item in enumerate(items, start=1):
        print(f'{index}. {label(item)}')
    number = int(input('Номер в списке: '))
    if not 1 <= number <= len(items):
        raise ValueError('Нет объекта с таким номером в списке')
    return items[number - 1]


def booking_label(system, booking):
    return (f'{system.events[booking.event_id].title}, '
            f'{system.customers[booking.customer_id].name}, '
            f'{booking.quantity} бил., {booking.total:.2f} руб., {booking.status.value}')


def run():
    system = BookingSystem()
    menu = '''
1 — Добавить площадку   2 — Добавить мероприятие   3 — Добавить клиента
4 — Список мероприятий  5 — Забронировать         6 — Отменить бронь
7 — Список броней       8 — Сохранить             9 — Загрузить
0 — Выход (сначала сохраните данные)
'''
    while True:
        try:
            print(menu)
            command = input('Команда: ').strip()
            if command == '0':
                return
            if command == '1':
                venue = Venue(input('Название: '), input('Адрес: '), int(input('Вместимость: ')))
                system.add_venue(venue)
                print(f'Площадка добавлена: {venue.name}')
            elif command == '2':
                print('Выберите площадку:')
                venue = select_item(system.venues, lambda v: f'{v.name}, {v.address}')
                event = Event(input('Название: '), venue.id,
                              datetime.fromisoformat(input('Дата (2027-05-20T19:00): ')),
                              Decimal(input('Цена в рублях (1500.00): ')))
                system.add_event(event)
                print(f'Мероприятие добавлено: {event.title}')
            elif command == '3':
                customer = Customer(input('Имя: '), input('Email: '))
                system.add_customer(customer)
                print(f'Клиент добавлен: {customer.name}')
            elif command == '4':
                for index, event in enumerate(system.events.values(), start=1):
                    print(f'{index}. {event.title}, {event.starts_at.isoformat()}, '
                          f'{event.price:.2f} руб., свободно: {system.available_seats(event.id)}')
            elif command == '5':
                print('Выберите мероприятие:')
                event = select_item(system.events, lambda e: f'{e.title}, {e.starts_at.isoformat()}')
                print('Выберите клиента:')
                customer = select_item(system.customers, lambda c: f'{c.name}, {c.email}')
                booking = system.book(event.id, customer.id, int(input('Количество билетов: ')))
                print(f'Номер брони: {booking.id}, сумма: {booking.total:.2f} руб.')
            elif command == '6':
                print('Выберите бронь для отмены:')
                booking = select_item(system.bookings, lambda b: booking_label(system, b))
                system.cancel(booking.id)
                print('Бронирование отменено.')
            elif command == '7':
                for index, booking in enumerate(system.bookings.values(), start=1):
                    print(f'{index}. {booking_label(system, booking)}')
            elif command in ('8', '9'):
                format_name = input('Формат (json/xml): ').strip().lower()
                if format_name not in ('json', 'xml'):
                    raise ValueError('Выберите json или xml')
                storage = JsonStorage() if format_name == 'json' else XmlStorage()
                path = input('Путь к файлу: ')
                if command == '8':
                    storage.save(system, path)
                else:
                    system = storage.load(path)
                print('Данные сохранены.' if command == '8' else 'Данные загружены.')
            else:
                raise ValueError('Неизвестная команда')
        except (BookingError, StorageError, ValueError, InvalidOperation) as exc:
            print(f'Ошибка: {exc}. Можно повторить операцию.')
        except (EOFError, KeyboardInterrupt):
            print('\nРабота завершена. Несохранённые изменения не записаны.')
            return


if __name__ == '__main__':
    run()
