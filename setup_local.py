"""Create local credentials once; never print credentials."""
import json
from pathlib import Path
import secrets

root=Path(__file__).resolve().parent
path=root/'config.local.json'
if not path.exists():
    with path.open('x',encoding='utf-8') as f:
        json.dump({'host':'127.0.0.1','port':8765,'token':secrets.token_urlsafe(48)},f)
    print('Created local config; token not displayed.')
else: print('Existing config preserved.')
