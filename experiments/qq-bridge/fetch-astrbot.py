"""Fetch a fixed official AstrBot release into the isolated QQ runtime."""
import hashlib
import json
from pathlib import Path
import re
import urllib.request
import zipfile

BASE=Path(__file__).resolve().parents[2]/'qq-runtime'
DOWNLOADS=BASE/'downloads'
DOWNLOADS.mkdir(parents=True,exist_ok=True)
if (BASE/'astrbot').exists():
    raise SystemExit('AstrBot checkout already exists; do not overwrite its runtime data.')
VERSION='v4.29.1'
def fetch(url,target):
    if target.is_file():return
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 OrangePi-Local-Setup'})
    with urllib.request.urlopen(req,timeout=90) as response,target.with_suffix('.partial').open('wb') as output:
        while chunk:=response.read(1024*1024):output.write(chunk)
    target.with_suffix('.partial').replace(target)
def extract(source,target,strip_root=False):
    with zipfile.ZipFile(source) as archive:
        for info in archive.infolist():
            parts=Path(info.filename).parts
            relative=Path(*parts[1:]) if strip_root else Path(*parts)
            dest=(target/relative).resolve()
            assert dest.is_relative_to(target.resolve()),info.filename
            if info.is_dir():dest.mkdir(parents=True,exist_ok=True)
            else:
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(archive.read(info))
records=[]
source=DOWNLOADS/f'AstrBot-{VERSION}-source.zip'
fetch(f'https://codeload.github.com/AstrBotDevs/AstrBot/zip/refs/tags/{VERSION}',source)
extract(source,BASE/'astrbot',True)
records.append({'kind':'source','version':VERSION,'sha256':hashlib.file_digest(source.open('rb'),'sha256').hexdigest(),'bytes':source.stat().st_size})
print('ASTRBOT_SOURCE_READY',VERSION,source.stat().st_size,flush=True)
dashboard=DOWNLOADS/f'AstrBot-{VERSION}-dashboard.zip'
url=f'https://github.com/AstrBotDevs/AstrBot/releases/download/{VERSION}/{dashboard.name}'
try:
    fetch(url,dashboard)
except Exception as error:
    print('DASHBOARD_ASSET_DISCOVERY',type(error).__name__,flush=True)
    page=DOWNLOADS/f'AstrBot-{VERSION}-assets.html'
    fetch(f'https://github.com/AstrBotDevs/AstrBot/releases/expanded_assets/{VERSION}',page)
    matches=re.findall(r'href="([^"]+dashboard[^"?]*\.zip)"',page.read_text(encoding='utf-8'))
    assert matches,'No dashboard in official release assets'
    url='https://github.com'+matches[0]
    fetch(url,dashboard)
extract(dashboard,BASE/'astrbot/data')
records.append({'kind':'dashboard','version':VERSION,'url':url,'sha256':hashlib.file_digest(dashboard.open('rb'),'sha256').hexdigest(),'bytes':dashboard.stat().st_size})
(BASE/'astrbot-source-manifest.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
print('ASTRBOT_DASHBOARD_READY',dashboard.stat().st_size,flush=True)
