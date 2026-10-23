import argparse
import logging
import os
import getpass
import sys
import uvicorn
from pka import applog
from pka.web import create_app
from pka.auth import AuthStore, AuthError
from pka.config import data_dir


def main():
    parser = argparse.ArgumentParser(description='Local Project Knowledge Assistant')
    parser.add_argument('--demo',action='store_true',help='Use labelled example data and a simulated response; no external services.')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--reset-password', action='store_true', help='Reset the local owner password and revoke every session, using hidden terminal input.')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a port between 1024 and 65535.')
    if args.reset_password:
        if not sys.stdin.isatty():
            parser.error('Password recovery needs an interactive terminal with hidden input.')
        store = AuthStore(data_dir()/('demo.sqlite3' if args.demo else 'index.sqlite3'))
        password = getpass.getpass('New owner password (15–128 characters): ')
        if password != getpass.getpass('Confirm new password: '):
            parser.error('Passwords did not match. Nothing changed.')
        try:
            store.reset_password(password)
        except AuthError as exc:
            parser.error(str(exc))
        print('Owner password changed. All sessions have been signed out.')
        return
    # Never log upstream HTTP requests, credentials, source excerpts or questions.
    for name in ('httpx','httpcore','mcp'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    log_path = applog.setup()
    applog.event('app.start', port=args.port, demo=args.demo,
                 model=os.getenv('OLLAMA_MODEL','qwen3:1.7b'),
                 token='configured' if os.getenv('GITHUB_TOKEN') else 'none',
                 questions_logged=applog.log_questions())
    print(f'Open http://127.0.0.1:{args.port} — '+('EXAMPLE MODE' if args.demo else 'GitHub + local Ollama'))
    print(f'Debug log: {log_path}')
    try:
        app = create_app(args.demo)
        if not app.state.auth.configured():
            print(f'First sign-in: copy the one-time code from {app.state.auth.setup_path} into the setup form.')
        uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False,log_level='warning',proxy_headers=False)
    finally:
        applog.event('app.stop')

if __name__ == '__main__':
    main()
