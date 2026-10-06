import argparse
import logging
import os
import uvicorn
from pka import applog
from pka.web import create_app


def main():
    parser = argparse.ArgumentParser(description='Local Project Knowledge Assistant')
    parser.add_argument('--demo',action='store_true',help='Use labelled example data and a simulated response; no external services.')
    parser.add_argument('--port',type=int,default=8000)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a port between 1024 and 65535.')
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
        uvicorn.run(create_app(args.demo),host='127.0.0.1',port=args.port,access_log=False,log_level='warning')
    finally:
        applog.event('app.stop')

if __name__ == '__main__':
    main()
