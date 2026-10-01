"""One-time local setup. Valkyrie is the single source of configuration.

Creates or completes (never overwrites existing values, never prints secrets):
  config.local.json   host, port, token, approval_token, and a `surface` section the voice
                      Surface downloads at startup (so it needs no settings of its own)
  coding-projects.json  the approved projects, including Beldin himself ("self") so he can
                      improve his own code in a disposable copy and bring it to you for approval
  config.surface.env  the ONLY file a Surface machine needs (address + two credentials)

Usage: python setup_local.py [--lan-host 192.168.x.x] [--toolchain node=C:\\tools\\node.exe ...]
"""
import argparse
import json
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument('--lan-host', help='Valkyrie LAN address the Surface will use (also sets the listening host)')
ap.add_argument('--toolchain', action='append', default=[], metavar='ID=ABSOLUTE_PATH',
                help='provision a language toolchain for validation, e.g. node=C:\\tools\\node\\node.exe')
ap.add_argument('--relocate-coding-data', action='store_true', help='move an overlapping coding data_root outside the project')
args = ap.parse_args()

# ---- config.local.json ----
path = root / 'config.local.json'
cfg = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
created = not path.exists()
cfg.setdefault('host', args.lan_host or '127.0.0.1')
if args.lan_host: cfg['host'] = args.lan_host
cfg.setdefault('port', 8765)
cfg.setdefault('token', secrets.token_urlsafe(48))
cfg.setdefault('approval_token', secrets.token_urlsafe(48))
cfg.setdefault('surface', {})
path.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
print('Created local config; credentials not displayed.' if created else 'Local config completed/preserved.')

# ---- coding-projects.json: Beldin can work on himself, in a copy, with human approval ----
work = root.parent / 'beldin-coding-data'          # OUTSIDE the project so the copy can never nest
cp = root / 'coding-projects.json'
coding = json.loads(cp.read_text(encoding='utf-8')) if cp.exists() else {}
coding.setdefault('models', ['qwen3:8b'])
coding.setdefault('projects', {})
coding['projects'].setdefault('beldin', {'path': str(root), 'production': True, 'self': True})
coding.setdefault('data_root', str(work))
inside = Path(coding['data_root']).resolve()
if inside == root or root in inside.parents or inside in root.parents:
    # A coding data folder that overlaps the project makes the registry invalid ("invalid_project_registry"),
    # which is the usual reason self-improvement will not start. Self-improvement needs it outside.
    if args.relocate_coding_data:
        print(f"Moved coding data_root from {coding['data_root']} to {work}")
        coding['data_root'] = str(work)
    else:
        print(f"WARNING: coding data_root {coding['data_root']} overlaps the project; self-improvement cannot start. "
              f"Re-run with --relocate-coding-data to use {work}.")
coding.setdefault('max_attempts', 5)     # keeps trying in the copy until validated, then asks you
coding.setdefault('max_minutes', 60)
coding.setdefault('toolchains', {})
for item in args.toolchain:
    tool, _, exe = item.partition('=')
    if tool and Path(exe).is_absolute(): coding['toolchains'][tool] = exe
    else: print(f'Ignored toolchain {item!r}: use ID=ABSOLUTE_PATH')
cp.write_text(json.dumps(coding, indent=2), encoding='utf-8')
print('Coding projects ready. Beldin can propose improvements to himself; only you can approve them.')

# ---- the whole Surface configuration ----
host = cfg['host'] if cfg['host'] not in ('0.0.0.0', '::') else '<VALKYRIE-LAN-IP>'
if host in ('127.0.0.1', 'localhost'): host = '<VALKYRIE-LAN-IP>'
gen = root / 'config.surface.env'
gen.write_text(
    '# Everything a Surface machine needs. Copy to BELDIN\\.env on the Surface and keep it private.\n'
    '# All other behaviour (wake word, timeouts, memory, tools) is served by Valkyrie.\n'
    f"BELDIN_URL=http://{host}:{cfg['port']}\n"
    f"BELDIN_TOKEN={cfg['token']}\n"
    f"BELDIN_APPROVAL_TOKEN={cfg['approval_token']}\n", encoding='utf-8')
print(f'Wrote {gen.name} (contains secrets). Put its 3 lines in the Surface .env; edit the address if needed.')
