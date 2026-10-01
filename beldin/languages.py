"""Language registry: detection and validation commands for many languages.

Python runs from the copied sandbox runtime. Every other toolchain is OPERATOR-PROVISIONED:
coding-projects.json maps a tool id to an absolute executable path, for example
{"toolchains": {"node": "C:\\tools\\node\\node.exe"}}. Nothing is downloaded or installed, and a
language with no provisioned toolchain is reported as unavailable, never as verified.
Validation runs inside the same no-network AppContainer as Python tests.

Templates use {files}: the changed files of that language (relative paths).
"""
from pathlib import Path
import base64

# language -> (extensions, [(command_id, tool_id, argv_template, kind)])
# kind: 'test' proves behaviour; 'check' proves it builds/parses only.
LANGUAGES = {
    'python': (('.py',), []),   # built in: unittest / compileall from the sandbox runtime
    'javascript': (('.js', '.mjs', '.cjs'), [('node_check', 'node', ['--check', '{file}'], 'check'),
                                             ('node_test', 'node', ['--test'], 'test')]),
    'typescript': (('.ts', '.tsx'), [('tsc_check', 'tsc', ['--noEmit'], 'check')]),
    'go': (('.go',), [('go_vet', 'go', ['vet', './...'], 'check'), ('go_test', 'go', ['test', './...'], 'test')]),
    'rust': (('.rs',), [('cargo_check', 'cargo', ['check', '--offline'], 'check'),
                        ('cargo_test', 'cargo', ['test', '--offline'], 'test')]),
    'java': (('.java',), [('javac_check', 'javac', ['-proc:none', '-d', '.beldin-out', '{files}'], 'check')]),
    'kotlin': (('.kt', '.kts'), [('kotlinc_check', 'kotlinc', ['{files}', '-d', '.beldin-out'], 'check')]),
    'csharp': (('.cs',), [('dotnet_build', 'dotnet', ['build', '--no-restore'], 'check'),
                          ('dotnet_test', 'dotnet', ['test', '--no-restore'], 'test')]),
    'c': (('.c', '.h'), [('cc_check', 'gcc', ['-fsyntax-only', '{files}'], 'check')]),
    'cpp': (('.cpp', '.cc', '.cxx', '.hpp'), [('cxx_check', 'g++', ['-fsyntax-only', '{files}'], 'check')]),
    'ruby': (('.rb',), [('ruby_check', 'ruby', ['-c', '{file}'], 'check')]),
    'php': (('.php',), [('php_check', 'php', ['-l', '{file}'], 'check')]),
    'lua': (('.lua',), [('luac_check', 'luac', ['-p', '{files}'], 'check')]),
    'swift': (('.swift',), [('swiftc_check', 'swiftc', ['-parse', '{files}'], 'check')]),
    'shell': (('.sh', '.bash'), [('bash_check', 'bash', ['-n', '{file}'], 'check')]),
    'powershell': (('.ps1',), [('pwsh_check', 'pwsh', ['-NoProfile', '-Command',
        '$tokens=$null;$errors=$null;[System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$tokens,[ref]$errors)|Out-Null;if($errors.Count){exit 1}', '{file}'], 'check')]),
    'html_css_js_web': (('.html', '.css'), []),
    'sql': (('.sql',), []),
}


def detect(paths):
    """Languages present among the given relative paths, in registry order."""
    exts = {Path(p).suffix.lower() for p in paths}
    return [name for name, (known, _) in LANGUAGES.items() if exts & set(known)]


def commands(toolchains, languages):
    """{command_id: spec} for the given languages whose tool is provisioned; plus the unavailable list."""
    available, missing = {}, []
    for name in languages:
        if name != 'python' and not LANGUAGES.get(name, ((), []))[1]:
            missing.append(dict(language=name,command=None,tool=None,reason='validator_not_available'))
        for cid, tool, argv, kind in LANGUAGES.get(name, ((), []))[1]:
            exe = (toolchains or {}).get(tool)
            if exe and Path(exe).is_absolute():
                available[cid] = dict(language=name, tool=tool, exe=str(exe), argv=list(argv), kind=kind)
            else:
                missing.append(dict(language=name, command=cid, tool=tool, reason='toolchain_not_provisioned'))
    return available, missing


def expand(spec, files):
    """List of concrete argv lists (never shell strings) plus whether anything applies."""
    exts = set(LANGUAGES[spec['language']][0])
    mine = sorted(f for f in files if Path(f).suffix.lower() in exts)
    if spec['tool']=='pwsh':
        commands=[]
        for filename in mine:
            literal=filename.replace("'","''")
            script=spec['argv'][2].replace('$args[0]', "'"+literal+"'")
            commands.append(['-NoProfile','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode('ascii')])
        return commands,bool(mine)
    if '{file}' in spec['argv']:  # one invocation per file
        return [[f if a == '{file}' else a for a in spec['argv']] for f in mine], bool(mine)
    out = []
    for a in spec['argv']:
        if a == '{files}': out.extend(mine)
        else: out.append(a)
    return [out], (bool(mine) or '{files}' not in spec['argv'])


def summary(toolchains):
    available, _ = commands(toolchains, LANGUAGES)
    return {name: {'extensions': list(ext),
                   'validation': [c[0] for c in cmds if c[0] in available] or
                                 (['unittest', 'compile'] if name == 'python' else []),
                   'unavailable_until_provisioned': sorted({c[1] for c in cmds if c[0] not in available})}
            for name, (ext, cmds) in LANGUAGES.items()}
