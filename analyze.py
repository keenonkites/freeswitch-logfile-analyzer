#!/usr/bin/env python

import argparse
from argparse import RawTextHelpFormatter
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

PROGRAMNAME = os.path.splitext(os.path.basename(__file__))[0]

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

class Line:
  """ Provides a 'Line' object to query various fields from logline. """

  def __init__(self, line:str) -> None:
    self.logline = line
    self.event_id = str(UUID(line.split()[0]))
    self.date = line.split()[1]
    self.time = line.split()[2]
    timestamp = f"{self.date} {self.time}"
    self.timestamp = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f').timestamp()

  def extract(self, pattern:str, ignore_case:bool = True) -> str:
    """ Extracts and arbitrary value from logline using supplied pattern and returns it as string. """
    re.compile(pattern)
    try:
      if ignore_case: return re.search(pattern, line, re.IGNORECASE).group(1)
      else: return re.search(pattern, line).group(1)
    except:
      return None

  def match(self, pattern:str, ignore_case:bool = True) -> bool:
    """ Returns True if pattern is found in log line """
    re.compile(pattern)
    if ignore_case:
      return bool(re.search(pattern, line, re.IGNORECASE))
    else:
      return bool(re.search(pattern, line))

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

epilog = f"""
Examples:
  {PROGRAMNAME} freeswitch.log
  {PROGRAMNAME} --output summary freeswitch.log
  {PROGRAMNAME} --encoding latin-1 freeswitch.log
  {PROGRAMNAME} --database log-$(date +'%Y-%m-%d-%H:%M:%S').db --encoding latin-1 freeswitch.log
"""

cli = argparse.ArgumentParser(
  prog = PROGRAMNAME,
  formatter_class=RawTextHelpFormatter,
  description = "Freeswitch logfile analyzer",
  epilog = epilog,
)

h = 'Path to Freeswitch logfile to analyze'
cli.add_argument('logfile', help=h)
h = 'If set, results will be stored into an SQLite3 database\nunder the given filename'
cli.add_argument('-d', '--database', help=h)
h = 'Encoding of the log file'
cli.add_argument('-e', '--encoding', default='ascii', help=h)
h = 'Print selected results to STDOUT'
cli.add_argument('-o', '--output', choices=['all','events','summary'], default='all', help=h)
args = cli.parse_args()

# Initialisierung der Events
events = Events()

with open(args.logfile, encoding=args.encoding) as f:
  for line in f:
    try:
      log = Line(line)
    except:
      continue

    if log.event_id not in events.events:
      event = Event(event_id=log.event_id, start=log.timestamp)
      events.events[log.event_id] = event

    event = events.events[log.event_id]

    event.cpu_load = 100 - float(log.extract(r' ([0-9.]+?)\% '))
    event.calling_party_number = log.extract(r'sofia/external/(.+?) ')
    event.inbound_client_ip = log.extract(r'receiving invite from (.+?):')
    if log.match(r'New Channel'): event.event_type = 'call'
    if log.match(r'sending invite call-id'): event.call_direction = 'outbound'
    if log.match(r'receiving invite'): event.call_direction = 'inbound'
    if log.match(r'Callstate Change'): event.callstate_changes.append(log.extract(r'Callstate Change (.+?)$'))
    if log.match(r'state change') and log.match(r' -> '): event.state_changes.append(log.extract(r'state change (.+?)$'))

    event.end = log.timestamp
    event.duration = event.end - event.start

    if not events.event_summary.logstart: events.event_summary.logstart = log.timestamp
    events.event_summary.logend = log.timestamp
    events.event_summary.logperiod = events.event_summary.logend - events.event_summary.logstart

  total_event_seconds = 0
  total_call_seconds = 0
  cpu_sum = 0
  if args.database: db = init_db(args.database)
  for k,v in events.events.items():
    events.event_summary.number_of_events = events.event_summary.number_of_events + 1
    total_event_seconds = total_event_seconds + v.duration
    if v.event_type == 'call':
      events.call_summary.number_of_calls = events.call_summary.number_of_calls + 1
      total_call_seconds = total_call_seconds + v.duration
    if v.call_direction == 'outbound': events.call_summary.number_of_outbound_calls = events.call_summary.number_of_outbound_calls + 1
    if v.call_direction == 'inbound': events.call_summary.number_of_inbound_calls = events.call_summary.number_of_inbound_calls + 1
    if args.database: store_event(v.to_dict(), db)
    cpu_sum = cpu_sum + v.cpu_load
    if v.event_type == 'call':
      total_call_seconds = total_call_seconds + v.duration

  events.event_summary.average_event_duration = total_event_seconds / events.event_summary.number_of_events
  events.event_summary.average_cpu_load = cpu_sum / events.event_summary.number_of_events

  acd = total_call_seconds / events.call_summary.number_of_calls
  events.call_summary.average_call_duration = acd
  events.call_summary.calls_per_second = (events.call_summary.number_of_calls * acd) / events.event_summary.logperiod

  if args.output == 'events':
    print(json.dumps(events.events.to_dict(), default=str, indent=2))
  elif args.output == 'summary':
    print(json.dumps(events.event_summary.to_dict()))
    print(json.dumps(events.call_summary.to_dict()))
  else:
    print(json.dumps(events.to_dict(), default=str, indent=2))

