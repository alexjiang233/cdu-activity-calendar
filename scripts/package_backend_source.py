"""Copy an explicit source-only release into a clean Git checkout. Never copy runtime data."""
import hashlib
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def package(target):
    target=Path(target).resolve()
    if target==ROOT or not (target/'.git').exists():raise SystemExit('Target must be a separate Git checkout.')
    protected={name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in ('README.md','index.html')}
    files=[]
    for base in ('backend','frontend/src','deploy'):
        for path in (ROOT/base).rglob('*'):
            if not path.is_file():continue
            rel=path.relative_to(ROOT)
            if any(p in rel.parts for p in ('__pycache__','staticfiles','media','admin')):continue
            if path.name=='.env.example' or path.suffix in ('.py','.html','.css','.js','.txt','.service','.md') or path.name=='Caddyfile':
                files.append(rel)
    files += [Path(p) for p in ('frontend/build.py','scripts/launch_admin.py','scripts/package_backend_source.py',
        '打开活动管理.vbs','.github/workflows/backend.yml','docs/backend/GETTING-STARTED.md') if (ROOT/p).exists()]
    for rel in files:
        destination=target/rel;destination.parent.mkdir(parents=True,exist_ok=True)
        content=(ROOT/rel).read_text(encoding='utf-8')
        normalized='\n'.join(line.rstrip() for line in content.splitlines()).rstrip()
        destination.write_text(normalized+'\n' if normalized else '',encoding='utf-8',newline='\n')
    # Merge ignores rather than replacing the existing static site's rules.
    ignore=target/'.gitignore'
    current=ignore.read_text(encoding='utf-8') if ignore.exists() else ''
    for line in (ROOT/'.gitignore').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#') and line not in current.splitlines():current+='\n'+line
    ignore.write_text(current.rstrip()+'\n',encoding='utf-8',newline='\n')
    for name,digest in protected.items():
        if hashlib.sha256((target/name).read_bytes()).hexdigest()!=digest:raise SystemExit('Protected file changed: '+name)
    print(f'Copied {len(files)} source files; README and live index unchanged; no DB, accounts, sessions or raw archives.')


if __name__=='__main__':package(sys.argv[1])
