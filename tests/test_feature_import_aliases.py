from pka import diagram, facts, features
from pka.config import now
from pka.index import Index, chunk_file


def test_aliased_module_is_reached_only_by_handlers_using_its_alias(tmp_path):
    index = Index(tmp_path / 'index.sqlite3')
    files = {
        'admin/main.py':'import database as db\n@app.get("/orders")\ndef orders():\n    return db.orders()\n@app.get("/health")\ndef health():\n    return {"ok": True}\n',
        'admin/database.py':'def orders():\n    return []\n',
    }
    scan = {'repo':'acme/shop','commit':'a'*40,'status':'complete','finished':now()}
    scan['id'] = index.new_scan(scan)
    index.activate(scan['id'], [c for path,text in files.items() for c in chunk_file(path,text)], scan)
    grouped = {f['id']:f['_detail']['files'] for f in features.derive(index,scan,facts.derive(index,scan))['features']}
    assert 'admin/database.py' in grouped['orders']
    assert 'admin/database.py' not in grouped['health']


def test_from_import_alias_resolves_original_module_and_preserves_source_boundary():
    table = diagram._lookup(['app/users.py', 'local://abc/app/users.py'])
    assert diagram.import_bindings('routes.py', [(1,'from app import users as user_api')], table) == [('user_api','app/users.py',1)]
    assert diagram.import_bindings('local://abc/routes.py', [(1,'from app import users as user_api')], table) == [('user_api','local://abc/app/users.py',1)]
