"""Run the app's access checks on a disposable copy of the saved index."""
import argparse
import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from pka.config import data_dir, now
from pka.connectors.base import SourceError
from pka.index import Index
from pka.service import Service


async def check_saved_access(db_path, connector_factory=None):
    db_path = Path(db_path)
    report = {'task_id':'5.3', 'started_at':now(), 'status':'blocked',
              'mode':'live read-only checks on a disposable index copy',
              'coverage':'Current saved Jira issues and Slack channels. Remote revocation is not performed.'}
    if not db_path.is_file():
        return {**report, 'reason':'No saved index exists.', 'finished_at':now()}
    with TemporaryDirectory(prefix='pka-access-') as folder:
        copy = Path(folder) / 'index.sqlite3'
        with closing(sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(copy)) as destination:
                source.backup(destination)
        index = Index(copy)
        scan = index.active_scan()
        if not scan:
            return {**report, 'reason':'No active scan exists.', 'finished_at':now()}
        paths = index.indexed_paths(scan['id'])
        counts = {name:sum(p.startswith(name+'/') for p in paths) for name in ('jira','slack')}
        report['saved_sources'] = {'jira_issues':counts['jira'], 'slack_channels':counts['slack']}
        if not all(counts.values()):
            return {**report, 'reason':'Import both Jira and Slack before checking task 5.3.', 'finished_at':now()}
        service = Service(index, **({'connector_factory':connector_factory} if connector_factory else {}))
        try:
            await service.check_external_access(scan)
            report['status'] = 'passed'
        except SourceError as exc:
            report['error_code'] = exc.code if exc.code in {'access_denied','scope','stale','access_unverified'} else 'access_unverified'
            report['reason'] = ('Access or saved content could not be verified. Check Connections and read the affected source again.')
        except Exception:
            report['error_code'] = 'unexpected'
            report['reason'] = 'The access check could not finish. No source response was recorded.'
    report['finished_at'] = now()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=data_dir()/'index.sqlite3')
    parser.add_argument('--output', type=Path, required=True, help='Save counts and results without source content or credentials.')
    args = parser.parse_args(argv)
    report = asyncio.run(check_saved_access(args.db))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print('Task 5.3 access check: ' + report['status'])
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
