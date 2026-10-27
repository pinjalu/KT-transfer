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
from pka.deployment import configure
from pka.runtime_lock import data_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local Project Knowledge Assistant')
    parser.add_argument('--demo',action='store_true',help='Use labelled example data and a simulated response; no external services.')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--host', default='127.0.0.1', help='Loopback, or a specific private IPv4 address for team HTTPS.')
    parser.add_argument('--team-origin', default='', help='Exact HTTPS address the team will use, including the port.')
    parser.add_argument('--ssl-certfile', help='PEM certificate issued for the team hostname by a trusted CA.')
    parser.add_argument('--ssl-keyfile', help='Matching PEM private key, stored only on the host.')
    parser.add_argument('--reset-password', action='store_true', help='Reset the local owner password and revoke owner sessions, using hidden terminal input.')
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a port between 1024 and 65535.')
    if args.reset_password:
        if not sys.stdin.isatty():
            parser.error('Password recovery needs an interactive terminal with hidden input.')
        try:
            with data_lock(data_dir()):
                store = AuthStore(data_dir()/('demo.sqlite3' if args.demo else 'index.sqlite3'))
                password = getpass.getpass('New owner password (15–128 characters): ')
                if password != getpass.getpass('Confirm new password: '):
                    parser.error('Passwords did not match. Nothing changed.')
                store.reset_password(password)
        except (AuthError, RuntimeError) as exc:
            parser.error(str(exc))
        print('Owner password changed. All owner sessions have been signed out.')
        return
    try:
        hosting = configure(args.host, args.port, args.team_origin, args.ssl_certfile, args.ssl_keyfile)
    except ValueError as exc:
        parser.error(str(exc))
    # Never log upstream HTTP requests, credentials, source excerpts or questions.
    for name in ('httpx','httpcore','mcp'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    log_path = applog.setup()
    applog.event('app.start', port=args.port, demo=args.demo,
                 model=os.getenv('OLLAMA_MODEL','qwen3:1.7b'),
                 token='configured' if os.getenv('GITHUB_TOKEN') else 'none',
                 questions_logged=applog.log_questions())
    print(f'Open {hosting.url} — '+('EXAMPLE MODE' if args.demo else 'GitHub + local Ollama'))
    print(f'Debug log: {log_path}')
    try:
        with data_lock(data_dir()):
            app = create_app(args.demo, hosting=hosting)
            if not app.state.auth.configured():
                print(f'First sign-in: copy the one-time code from {app.state.auth.setup_path} into the setup form.')
            uvicorn.run(app, host=hosting.host, port=hosting.port, access_log=False,
                        log_level='warning', proxy_headers=False,
                        ssl_certfile=hosting.certfile, ssl_keyfile=hosting.keyfile)
    except RuntimeError as exc:
        parser.exit(1, str(exc) + '\n')
    finally:
        applog.event('app.stop')

if __name__ == '__main__':
    main()
