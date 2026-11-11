"""Fixed model assets, resumable downloads and receipts on the free data disk."""
import concurrent.futures
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

PROJECT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((PROJECT / 'sources.json').read_text(encoding='utf-8'))
DATA = Path(os.environ.get('H3_DATA_ROOT', '/root/autodl-tmp/minimax-h3-30s'))
STATUS = DATA / 'status.json'
LOCK = threading.RLock()
CURRENT = {}
PROGRESS = {}


def status(**values):
    with LOCK:
        CURRENT.update(values, updated_at=time.time())
        DATA.mkdir(parents=True, exist_ok=True)
        temp = STATUS.with_suffix('.tmp')
        temp.write_text(json.dumps(CURRENT, ensure_ascii=False), encoding='utf-8')
        temp.replace(STATUS)


def progress(spec, completed, speed=0):
    with LOCK:
        PROGRESS[spec['path']] = completed
        overall = sum(PROGRESS.values())
        status(stage='downloading', file=Path(spec['path']).name, completed=completed,
               total=spec['bytes'], bytes_per_second=round(speed),
               overall_completed=overall, overall_total=sum(item['bytes'] for item in CONFIG['models']))


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def fetch(spec):
    relative = spec['path']
    target = DATA / 'models' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    receipt = target.with_suffix('.verified.json')
    if target.exists():
        stat = target.stat()
        recorded = json.loads(receipt.read_text()) if receipt.exists() else {}
        if (stat.st_size == spec['bytes'] and recorded.get('sha256') == spec['sha256']
                and recorded.get('mtime_ns') == stat.st_mtime_ns):
            progress(spec, spec['bytes'])
            return target
        if stat.st_size == spec['bytes'] and digest(target) == spec['sha256']:
            receipt.write_text(json.dumps({**spec, 'mtime_ns': stat.st_mtime_ns}))
            progress(spec, spec['bytes'])
            return target
        raise RuntimeError(f'Existing model is inconsistent; preserved for inspection: {relative}')

    chunk_size = 8 * 1024 * 1024
    part = target.with_suffix('.download.part')
    state_path = target.with_suffix('.download.json')
    state = {'sha256': spec['sha256'], 'bytes': spec['bytes'], 'chunk_size': chunk_size, 'done': []}
    if part.exists() and state_path.exists():
        previous = json.loads(state_path.read_text())
        if (all(previous.get(key) == state[key] for key in ('sha256', 'bytes', 'chunk_size'))
                and part.stat().st_size == spec['bytes']):
            state = previous
        else:
            raise RuntimeError(f'Incompatible download state preserved: {relative}')
    else:
        if shutil.disk_usage(DATA).free < spec['bytes'] + 1024 ** 3:
            raise RuntimeError('Data disk needs at least the remaining model size plus 1GiB; no paid expansion requested.')
        with part.open('wb') as stream:
            stream.truncate(spec['bytes'])
    done = set(state['done'])
    failures = []
    candidates = []
    if spec.get('modelscope_revision'):
        candidates.append(f"https://modelscope.cn/models/{CONFIG['model_repository']}/resolve/{spec['modelscope_revision']}/{quote(relative)}")
    candidates.extend(f"{endpoint}/{CONFIG['model_repository']}/resolve/{CONFIG['model_revision']}/{quote(relative)}"
                      for endpoint in ('https://hf-mirror.com', 'https://huggingface.co'))
    for url in candidates:
        try:
            with urlopen(Request(url + '?download=true', method='HEAD'), timeout=20) as response:
                resolved = response.geturl()
            break
        except Exception as error:
            failures.append(type(error).__name__)
    else:
        raise RuntimeError('Model endpoints unavailable: ' + ', '.join(failures))

    stopped = threading.Event()

    def download(offset):
        end = min(offset + chunk_size, spec['bytes']) - 1
        for attempt in range(5):
            if stopped.is_set():
                raise RuntimeError('Transfer cancelled after a range failed')
            try:
                request = Request(resolved, headers={'Range': f'bytes={offset}-{end}', 'User-Agent': 'H3-30s/1.0'})
                with urlopen(request, timeout=20) as response:
                    if response.status != 206 or response.headers.get('Content-Range') != f"bytes {offset}-{end}/{spec['bytes']}":
                        raise ValueError('Server did not return the requested byte range')
                    block = response.read(end - offset + 2)
                if len(block) != end - offset + 1:
                    raise ValueError('Incomplete range')
                with part.open('r+b') as stream:
                    stream.seek(offset)
                    stream.write(block)
                return len(block)
            except Exception:
                if attempt == 4:
                    raise
                stopped.wait(min(8, 2 ** attempt))

    completed = sum(min(chunk_size, spec['bytes'] - offset) for offset in done)
    started, initial, logged = time.monotonic(), completed, 0
    progress(spec, completed)
    print('DOWNLOAD_START', relative, completed, spec['bytes'], flush=True)
    workers = min(32, max(1, int(os.environ.get('H3_DOWNLOAD_WORKERS', '16'))))
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {executor.submit(download, offset): offset
                   for offset in range(0, spec['bytes'], chunk_size) if offset not in done}
        for future in concurrent.futures.as_completed(futures):
            completed += future.result()
            done.add(futures[future])
            state['done'] = sorted(done)
            temporary_state = state_path.with_suffix('.tmp')
            temporary_state.write_text(json.dumps(state))
            temporary_state.replace(state_path)
            if time.monotonic() - logged > 5 or completed == spec['bytes']:
                speed = (completed - initial) / max(0.1, time.monotonic() - started)
                progress(spec, completed, speed)
                print('DOWNLOAD_PROGRESS', Path(relative).name, completed, spec['bytes'], round(speed / 1048576, 2), 'MiB/s', flush=True)
                logged = time.monotonic()
    finally:
        stopped.set()
        executor.shutdown(wait=True, cancel_futures=True)
    status(stage='verifying', file=Path(relative).name)
    print('HASH_VERIFY', relative, flush=True)
    if digest(part) != spec['sha256']:
        raise RuntimeError(f'Checksum mismatch; partial file retained for inspection: {relative}')
    part.replace(target)
    state_path.unlink()
    receipt.write_text(json.dumps({**spec, 'mtime_ns': target.stat().st_mtime_ns}))
    print('MODEL_VERIFIED', relative, flush=True)
    return target


def _prepare(comfy_root):
    DATA.mkdir(parents=True, exist_ok=True)
    def resolve(spec):
        mounted = Path('/.autodl-model/data') / CONFIG['model_repository'] / spec['path']
        # Read-only public assets use pinned filenames and expected file lengths.
        actual = mounted if mounted.is_file() and mounted.stat().st_size == spec['bytes'] else fetch(spec)
        return spec, actual
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        resolved = list(executor.map(resolve, CONFIG['models']))
    for spec, actual in resolved:
        link = comfy_root / 'models' / spec['path']
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink():
            if link.resolve() == actual.resolve():
                continue
            link.unlink()
        if link.exists():
            raise RuntimeError(f'Refusing to replace a real model file: {link}')
        link.symlink_to(actual)
    status(stage='models_ready', message='模型准备完成，正在启动30秒工作流。')
    return DATA


def prepare(comfy_root):
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / '.models.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _prepare(comfy_root)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--comfy-root', type=Path, default=Path('/root/H3-30s/ComfyUI'))
    args = parser.parse_args()
    try:
        prepare(args.comfy_root)
    except Exception as error:
        status(stage='error', message=str(error))
        raise
