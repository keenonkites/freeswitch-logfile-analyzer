#!/usr/bin/env python

from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List
import json
import os
import re
import sqlite3
import sys
from uuid import UUID

from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass
class Event:
  event_id: str
  start: float
  end: Optional[float] = None
  duration: Optional[float] = None
  event_type: Optional[str] = None
  cpu_load: Optional[float] = None
  calling_party_number: Optional[str] = None
  call_direction: Optional[str] = None
  inbound_client_ip: Optional[str] = None
  callstate_changes: List[str] = field(default_factory=list)
  state_changes: List[str] = field(default_factory=list)

  def to_dict(self):
    return {
      "event_id": self.event_id,
      "start": self.start,
      "end": self.end,
      "duration": self.duration,
      "event_type": self.event_type,
      "cpu_load": self.cpu_load,
      "calling_party_number": self.calling_party_number,
      "call_direction": self.call_direction,
      "inbound_client_ip": self.inbound_client_ip,
      "callstate_changes": self.callstate_changes,
      "state_changes": self.state_changes,
    }

@dataclass
class EventSummary:
  average_event_duration: float = 0
  number_of_events: int = 0
  logstart: Optional[float] = None
  logend: Optional[float] = None
  logperiod: Optional[float] = None
  average_cpu_load: Optional[float] = 0

  def to_dict(self):
    return {
      "average_event_duration": self.average_event_duration,
      "number_of_events": self.number_of_events,
      "logstart": self.logstart,
      "logend": self.logend,
      "logperiod": self.logperiod,
      "average_cpu_load": self.average_cpu_load,
    }

@dataclass
class CallSummary:
  number_of_calls: int = 0
  number_of_outbound_calls = 0
  number_of_inbound_calls = 0
  average_call_duration: float = 0
  calls_per_second: float = 0

  def to_dict(self):
    return {
      "number_of_calls": self.number_of_calls,
      "number_of_outbound_calls": self.number_of_outbound_calls,
      "number_of_inbound_calls": self.number_of_inbound_calls,
      "average_call_duration": self.average_call_duration,
      "calls_per_second": self.calls_per_second,
    }

@dataclass
class Events:
  events: Dict[str, Event] = field(default_factory=dict)
  event_summary: EventSummary = field(default_factory=EventSummary)
  call_summary: CallSummary = field(default_factory=CallSummary)

  def to_dict(self):
    return {
      "events": {key: value.to_dict() for key, value in self.events.items()},
      "event_summary": self.event_summary.to_dict(),
      "call_summary": self.call_summary.to_dict(),
    }

def init_db(db_file:str='events.db') -> sqlite3.Cursor:
  import contextlib

  with contextlib.suppress(FileNotFoundError):
    os.remove(db_file)

  db_connection = sqlite3.connect(db_file, isolation_level=None)
  db_cursor = db_connection.cursor()

  db_cursor.execute('''
    CREATE TABLE IF NOT EXISTS events (
      event_id TEXT PRIMARY KEY,
      start REAL,
      end REAL,
      duration REAL,
      event_type TEXT,
      cpu_load REAL,
      calling_party_number TEXT,
      call_direction TEXT,
      inbound_client_ip TEXT
    )
  ''')

  db_cursor.execute('''
    CREATE TABLE IF NOT EXISTS state_changes (
      event_id TEXT,
      state_before TEXT,
      state_after TEXT
    )
  ''')

  return db_cursor

def store_event(event:dict, db_cursor:sqlite3.Cursor) -> None:
  k = ', '.join(list(event.keys())[:-2])
  v = ', '.join('"'+str(value)+'"' if value is not None else 'NULL' for value in list(event.values())[:-2])
  sql = f'INSERT OR REPLACE INTO events ({k}) VALUES ({v})'
  db_cursor.execute(sql)

  for state in event['state_changes']:
    (state_before, state_after) = state.split(' -> ')
    sql = f'INSERT INTO state_changes (event_id, state_before, state_after) VALUES ("%s", "%s", "%s")' % (event['event_id'], state_before, state_after)
    db_cursor.execute(sql)

# Initialisierung der Events
events = Events()

with open(sys.argv[1], encoding='latin-1') as f:
  db = init_db()

  for line in f:
    event = None
    event_id = None

    try:
      event_id = str(UUID(line.split()[0]))
    except ValueError:
      continue

    try:
      date = line.split()[1]
      time = line.split()[2]
      timestamp = f"{date} {time}"
    except IndexError:
      continue

    try:
      timestamp = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f').timestamp()
    except ValueError:
      continue

    if event_id not in events.events:
      event = Event(event_id=event_id, start=timestamp)
      events.events[event_id] = event
      events.event_summary.number_of_events += 1

    event = events.events[event_id]
    event.cpu_load = 100 - float(line.split()[3].rstrip('%'))

    if 'New Channel' in line:
      events.call_summary.number_of_calls += 1
      event.event_type = 'call'
      try:
        event.calling_party_number = re.search('sofia/external/(.+?) ', line).group(1)
      except AttributeError:
        pass

    event.end = timestamp
    event.duration = event.end - event.start
    events.event_summary.average_event_duration = (events.event_summary.average_event_duration + event.duration) / 2

    if 'sending invite call-id' in line:
      event.call_direction = 'outbound'
      events.call_summary.number_of_outbound_calls = events.call_summary.number_of_outbound_calls + 1

    if 'receiving invite' in line:
      event.call_direction = 'inbound'
      events.call_summary.number_of_inbound_calls = events.call_summary.number_of_inbound_calls + 1

    try:
      event.inbound_client_ip = re.search('receiving invite from (.+?):', line).group(1)
    except AttributeError:
      pass

    if 'Callstate Change' in line:
      event.callstate_changes.append(re.search(r'Callstate Change (.+?)$', line).group(1))

    if 'state change' in line.lower() and ' -> ' in line:
      event.state_changes.append(re.search(r'state change (.+?)$', line, re.IGNORECASE).group(1))

    if events.event_summary.logstart is None:
      events.event_summary.logstart = timestamp

    events.event_summary.logend = timestamp
    events.event_summary.logperiod = events.event_summary.logend - events.event_summary.logstart


  total_call_seconds = 0
  cpu_sum = 0
  for k,v in events.events.items():
    store_event(v.to_dict(), db)
    cpu_sum = cpu_sum + v.cpu_load
    if v.event_type == 'call':
      total_call_seconds = total_call_seconds + v.duration

  events.event_summary.average_cpu_load = cpu_sum / events.event_summary.number_of_events

  acd = total_call_seconds / events.call_summary.number_of_calls
  events.call_summary.average_call_duration = acd
  events.call_summary.calls_per_second = (events.call_summary.number_of_calls * acd) / events.event_summary.logperiod

  print(json.dumps(events.to_dict(), default=str, indent=2))
