"""Build a clean installable ZIP; never include fixtures, local config or history."""
import ast
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'sample_excel_sync'


def main():
    manifest = ast.literal_eval((MODULE / '__manifest__.py').read_text(encoding='utf-8'))
    for relative in manifest['data']:
        if not (MODULE / relative).is_file():
            raise ValueError(f'Missing manifest resource: {relative}')
    output = ROOT / 'dist' / 'sample_excel_sync.zip'
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(MODULE.rglob('*')):
            if path.is_file() and path.suffix in ('.py', '.xml', '.csv', '.po', '.md') and '__pycache__' not in path.parts:
                archive.write(path, path.relative_to(ROOT).as_posix())
        for name in ('LICENSE', 'COPYING', 'README.md', 'README.zh-CN.md', 'docs/acceptance.md',
                     'docs/offline-registration.md'):
            archive.write(ROOT / name, f'sample_excel_sync/{name}')
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')
    print(f'{output.name}: {digest}')


if __name__ == '__main__':
    main()
