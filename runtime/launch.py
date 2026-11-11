"""Expand the bundled runtime on the data disk, keeping the saved image small."""
import fcntl
import os
from pathlib import Path
import subprocess
import tarfile

ROOT = Path('/root/H3-30s')
DATA = Path('/root/autodl-tmp/minimax-h3-30s')
DATA.mkdir(parents=True, exist_ok=True)
with (DATA/'.runtime.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    runtime = DATA/'runtime-venv'
    if not (runtime/'.unpacked-v1').exists():
        if runtime.exists():
            raise SystemExit('An unfinished runtime exists; inspect it before retrying.')
        staging = DATA/'runtime-unpacking'
        staging.mkdir(exist_ok=True)
        with tarfile.open(ROOT/'runtime-venv.tar.gz') as archive:
            archive.extractall(staging, filter='data')
        (staging/'bin/python').symlink_to('/root/miniconda3/bin/python')
        for name in ('python3', 'python3.12'):
            (staging/'bin'/name).symlink_to('python')
        (staging/'.unpacked-v1').write_text('1\n')
        staging.rename(runtime)
    link = ROOT/'.venv'
    if link.is_symlink():
        if link.resolve() != runtime.resolve():
            raise SystemExit('Runtime path points to another environment')
    elif not link.exists():
        link.symlink_to(runtime, target_is_directory=True)
    else:
        raise SystemExit('A runtime directory exists at the image path; preserving it')
os.execv(str(runtime/'bin/python'), [str(runtime/'bin/python'),
         '/root/autodl-minimax-h3-30s/runtime/bootstrap.py', *os.sys.argv[1:]])
