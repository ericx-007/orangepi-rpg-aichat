"""Use synthetic identities, never a deployment's account configuration."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ['ORANGEPI_ROLEPLAY_CONFIG'] = str(ROOT / 'tests/fixtures/settings.json')
sys.path.insert(0, os.environ.get('ASTRBOT_SOURCE', str(ROOT / 'qq-runtime/astrbot')))
