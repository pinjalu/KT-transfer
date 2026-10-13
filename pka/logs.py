"""Read the application log from the terminal.

`pka/applog.py` has always written a structured line per event to data/logs/pka.log, but the
only way to read it was to open the file and scroll. That file is deliberately not served over
HTTP, because it records paths and configuration that the browser has no business fetching, so
the reader belongs here instead.

    python -m pka.logs                  the last 40 events
    python -m pka.logs -n 200           the last 200
    python -m pka.logs -e ask           only events whose name starts with "ask"
    python -m pka.logs -g chat_bridge   only lines containing that text
    python -m pka.logs --errors         warnings and errors only
    python -m pka.logs --follow         keep printing as new events arrive
    python -m pka.logs --last-ask       the full trace of the most recent question
    python -m pka.logs --path           print where the log file is and stop
"""
import argparse
import re
import sys
import time

from pka.config import log_dir

# "2026-10-12 10:30:00,123 INFO  ask.terms        asked=hello used=hello"
LINE = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ (\w+)\s+(\S+)\s*(.*)$')


def parse(line: str) -> dict | None:
    """One log line split into its parts, or None for a traceback continuation line."""
    m = LINE.match(line.rstrip('\n'))
    if not m:
        return None
    stamp, level, name, rest = m.groups()
    return {'time': stamp, 'level': level, 'event': name, 'fields': rest, 'raw': line.rstrip('\n')}


def read(path) -> list[str]:
    if not path.exists():
        return []
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.readlines()


def keep(line: str, event: str, grep: str, errors: bool) -> bool:
    """Whether one line survives the filters. A traceback line follows whatever it belongs to."""
    parsed = parse(line)
    if parsed is None:
        # Continuation of a traceback. Only shown when nothing is being filtered out, because
        # a stack trace attached to a hidden error is noise on its own.
        return not (event or grep or errors)
    if errors and parsed['level'] not in ('WARNING', 'ERROR', 'CRITICAL'):
        return False
    if event and not parsed['event'].startswith(event):
        return False
    if grep and grep.lower() not in line.lower():
        return False
    return True


def last_ask(lines: list[str]) -> list[str]:
    """Every line from the most recent ask.begin to the ask.end that closed it.

    This is the one view worth having built in. A question that came back wrong is explained
    by the terms it was reduced to, the files that were retrieved and the checks that ran, and
    those are four separate events that are tedious to find by eye.
    """
    start = None
    for i, line in enumerate(lines):
        parsed = parse(line)
        if parsed and parsed['event'] in ('ask.begin', 'ask.small_talk'):
            start = i
    if start is None:
        return []
    out = [lines[start]]
    for line in lines[start + 1:]:
        out.append(line)
        parsed = parse(line)
        if parsed and parsed['event'] == 'ask.end':
            break
    return out


def show(lines) -> None:
    for line in lines:
        sys.stdout.write(line if line.endswith('\n') else line + '\n')
    sys.stdout.flush()


def follow(path, event: str, grep: str, errors: bool) -> None:
    """Print new lines as they are written, the way tail -f does."""
    with open(path, encoding='utf-8', errors='replace') as fh:
        fh.seek(0, 2)
        try:
            while True:
                line = fh.readline()
                if not line:
                    time.sleep(0.4)
                    continue
                if keep(line, event, grep, errors):
                    show([line])
        except KeyboardInterrupt:
            pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog='python -m pka.logs', description='Read the application log.')
    p.add_argument('-n', '--lines', type=int, default=40, help='How many events to show. Default 40.')
    p.add_argument('-e', '--event', default='', help='Only events whose name starts with this, for example ask or scan.')
    p.add_argument('-g', '--grep', default='', help='Only lines containing this text, case insensitive.')
    p.add_argument('--errors', action='store_true', help='Warnings and errors only.')
    p.add_argument('--follow', action='store_true', help='Keep printing as new events arrive.')
    p.add_argument('--last-ask', action='store_true', help='The full trace of the most recent question.')
    p.add_argument('--path', action='store_true', help='Print the log file path and stop.')
    args = p.parse_args(argv)

    path = log_dir() / 'pka.log'
    if args.path:
        print(path)
        return 0
    if not path.exists():
        print(f'No log yet at {path}. Start the application once and it will be created.')
        return 1

    if args.follow:
        print(f'Following {path}. Ctrl+C to stop.')
        follow(path, args.event, args.grep, args.errors)
        return 0

    lines = read(path)
    chosen = last_ask(lines) if args.last_ask else [x for x in lines if keep(x, args.event, args.grep, args.errors)]
    if not args.last_ask:
        chosen = chosen[-args.lines:]
    if not chosen:
        print('Nothing matched. Try a wider filter, or --path to check which file is being read.')
        return 1
    show(chosen)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
