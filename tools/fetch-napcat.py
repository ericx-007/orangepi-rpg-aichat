"""Fetch the pinned official Windows Node runtime, excluding login state."""
import hashlib
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
base = ROOT / 'qq-runtime'
target = base / 'napcat'
if target.exists():
    raise SystemExit('NapCat already exists; do not overwrite an existing runtime.')
if shutil.disk_usage(ROOT).free < 1024 ** 3:
    raise SystemExit('Need at least 1 GiB free for the portable runtime download.')
downloads = base / 'downloads'
downloads.mkdir(parents=True, exist_ok=True)
name = 'NapCat.Shell.Windows.Node.zip'
expected = 'b88007a373a30deefb387e7cf17911752ff900bce22c534b3da6b644f5c6d0ae'
archive = downloads / name
if not archive.exists():
    request = urllib.request.Request('https://github.com/NapNeko/NapCatQQ/releases/download/v4.18.38/' + name,
                                     headers={'User-Agent': 'orangepi-rpg-aichat-setup'})
    temp = archive.with_suffix('.partial')
    with urllib.request.urlopen(request, timeout=90) as response, temp.open('wb') as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    temp.replace(archive)
with archive.open('rb') as stream:
    if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
        raise SystemExit('NapCat archive hash mismatch; do not extract it.')
with zipfile.ZipFile(archive) as source:
    for member in source.infolist():
        if not (target / member.filename).resolve().is_relative_to(target.resolve()):
            raise ValueError('Unsafe archive member')
    source.extractall(target)
if not (target / 'node.exe').is_file() or not (target / 'index.js').is_file():
    raise SystemExit('Unexpected upstream archive layout.')
print('Pinned NapCat Windows Node runtime ready. No QQ login has been performed.')
