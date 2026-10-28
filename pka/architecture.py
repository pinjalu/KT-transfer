"""Architecture derived from the current saved files, independently of generated prose."""
from pka import diagram, facts, roles
from pka.overview_context import source_systems


class SystemIndex:
    """Read-only, system-scoped view with numbered lines shared by the analysis passes."""
    def __init__(self, index, scan_id, paths):
        self.files = {path: index.file_lines(scan_id, path) for path in paths}

    def indexed_paths(self, scan_id):
        return list(self.files)

    code_paths = indexed_paths

    def file_lines(self, scan_id, path):
        return self.files.get(path, [])

    def source_blocks(self, scan_id, prefix):
        return 0


def derive(index, scan):
    systems = []
    for system in source_systems(index, scan, index.code_paths(scan['id'])):
        view = SystemIndex(index, scan['id'], system['paths'])
        found = facts.derive(view, scan)
        systems.append({'id':system['id'], 'name':system['name'], 'facts':found,
                        'diagrams':diagram.build(view, scan, found),
                        'roles':roles.describe(view, scan, found)})
    return {'systems':systems}
