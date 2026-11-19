"""Единая схема данных для JSON и XML; загрузка создаёт новую систему."""
from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import os
import tempfile
from uuid import UUID
import xml.etree.ElementTree as ET

from .models import Booking, BookingError, BookingStatus, Customer, Event, StorageError, Venue
from .service import BookingSystem


FIELDS = {
    'venues': ('id', 'name', 'address', 'capacity'),
    'events': ('id', 'title', 'venue_id', 'starts_at', 'price'),
    'customers': ('id', 'name', 'email'),
    'bookings': ('id', 'event_id', 'customer_id', 'quantity', 'unit_price', 'status'),
}


def to_data(system: BookingSystem) -> dict:
    data = {'version': 1}
    for group in FIELDS:
        data[group] = []
        for item in getattr(system, group).values():
            row = asdict(item)
            for key, value in row.items():
                if isinstance(value, datetime):
                    row[key] = value.isoformat()
                elif isinstance(value, Decimal):
                    row[key] = str(value)
                elif isinstance(value, BookingStatus):
                    row[key] = value.value
            data[group].append(row)
    return data


def _restore(model, row):
    """Только загрузчик восстанавливает сохранённый ID, конструкторы его не принимают."""
    identifier = row.pop('id')
    parsed = UUID(identifier)
    if parsed.version != 4 or str(parsed) != identifier:
        raise ValueError('ID должен быть UUID версии 4 в стандартной записи')
    instance = model(**row)
    object.__setattr__(instance, 'id', identifier)
    return instance


def from_data(data: dict) -> BookingSystem:
    if (not isinstance(data, dict) or set(data) != {'version', *FIELDS}
            or type(data['version']) is not int or data['version'] != 1):
        raise ValueError('Неверная схема или версия данных')
    system = BookingSystem()
    for group, fields in FIELDS.items():
        if not isinstance(data[group], list):
            raise ValueError(f'{group}: требуется массив')
        for source in data[group]:
            if not isinstance(source, dict) or set(source) != set(fields):
                raise ValueError(f'{group}: неверный набор полей')
            row = source.copy()
            for key, value in row.items():
                if key in ('capacity', 'quantity'):
                    if type(value) is not int:
                        raise ValueError(f'{key}: требуется целое число')
                elif not isinstance(value, str):
                    raise ValueError(f'{key}: требуется строка')
            if group == 'venues':
                system.add_venue(_restore(Venue, row))
            elif group == 'events':
                row['starts_at'] = datetime.fromisoformat(row['starts_at'])
                row['price'] = Decimal(row['price'])
                system.add_event(_restore(Event, row))
            elif group == 'customers':
                system.add_customer(_restore(Customer, row))
            else:
                row['unit_price'] = Decimal(row['unit_price'])
                row['status'] = BookingStatus(row['status'])
                system.restore_booking(_restore(Booking, row))
    return system


class FileStorage(ABC):
    @abstractmethod
    def encode(self, data: dict) -> str:
        pass

    @abstractmethod
    def decode(self, content: str) -> dict:
        pass

    def save(self, system: BookingSystem, path: str | Path):
        """Заменяет файл только после полной записи временного файла."""
        temporary = None
        try:
            target = Path(path)
            content = self.encode(to_data(system))
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=target.parent, delete=False) as stream:
                temporary = stream.name
                stream.write(content)
            os.replace(temporary, target)
        except (OSError, ValueError) as exc:
            raise StorageError(f'Не удалось сохранить файл: {exc}') from exc
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def load(self, path: str | Path) -> BookingSystem:
        try:
            return from_data(self.decode(Path(path).read_text(encoding='utf-8')))
        except (OSError, ValueError, TypeError, KeyError, InvalidOperation,
                ET.ParseError, BookingError) as exc:
            raise StorageError(f'Не удалось загрузить файл: {exc}') from exc


class JsonStorage(FileStorage):
    def encode(self, data: dict) -> str:
        return json.dumps(data, ensure_ascii=False, indent=2) + '\n'

    def decode(self, content: str) -> dict:
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f'Повтор поля: {key}')
                result[key] = value
            return result
        return json.loads(content, object_pairs_hook=unique_pairs)


class XmlStorage(FileStorage):
    def encode(self, data: dict) -> str:
        root = ET.Element('booking_system', version=str(data['version']))
        for group in FIELDS:
            container = ET.SubElement(root, group)
            for row in data[group]:
                item = ET.SubElement(container, group[:-1])
                for key, value in row.items():
                    ET.SubElement(item, key).text = str(value)
        ET.indent(root, space='  ')
        return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding='unicode') + '\n'

    def decode(self, content: str) -> dict:
        root = ET.fromstring(content)
        if (root.tag != 'booking_system' or root.attrib != {'version': '1'}
                or len(root) != len(FIELDS) or {c.tag for c in root} != set(FIELDS)):
            raise ValueError('Неверный корневой элемент XML')
        data = {'version': 1}
        for container in root:
            if container.attrib:
                raise ValueError('Лишние атрибуты XML')
            rows = []
            for item in container:
                if (item.tag != container.tag[:-1] or item.attrib
                        or len(item) != len(FIELDS[container.tag])
                        or {c.tag for c in item} != set(FIELDS[container.tag])):
                    raise ValueError('Неверная запись XML')
                row = {}
                for cell in item:
                    if cell.attrib or len(cell):
                        raise ValueError('Ожидалось простое поле XML')
                    value = cell.text or ''
                    row[cell.tag] = int(value) if cell.tag in ('quantity', 'capacity') else value
                rows.append(row)
            data[container.tag] = rows
        return data
