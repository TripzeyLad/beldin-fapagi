"""Windows AppContainer runner: no capabilities, private SID per execution.

Never falls back to an ordinary child process. Only the copied Python runtime
and disposable execution directory receive SID-specific filesystem grants.
"""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import subprocess
import time
import uuid


def run(runtime, workspace, argv, cancel=None, timeout=60, tool=None, tool_dirs=()):
    """Run `python -m argv` (default) or, with `tool`, an operator-provisioned executable.

    Tool mode is UNTESTED on real Windows here: the executable is launched by the sandbox's own
    Python inside the same AppContainer (no network, job-object limits) and its folder receives a
    read/execute grant for this run only.
    """
    if os.name != 'nt':
        raise RuntimeError('Windows AppContainer is required')
    if tool is not None:
        tool = Path(tool)
        if not tool.is_absolute() or not tool.is_file(): raise RuntimeError('Toolchain executable is not provisioned')
        tool_dirs = [Path(d).resolve() for d in (tool_dirs or [tool.parent])]
    runtime, workspace = Path(runtime).resolve(), Path(workspace).resolve()
    if not (runtime / 'python.exe').is_file():
        raise RuntimeError('Sandbox Python runtime is not provisioned')
    k = C.WinDLL('kernel32', use_last_error=True)
    u = C.WinDLL('userenv', use_last_error=True)
    a = C.WinDLL('advapi32', use_last_error=True)
    ptr = C.c_void_p
    class SI(C.Structure):
        _fields_ = [('cb', W.DWORD), ('reserved', W.LPWSTR), ('desktop', W.LPWSTR), ('title', W.LPWSTR),
                    ('x', W.DWORD), ('y', W.DWORD), ('xs', W.DWORD), ('ys', W.DWORD),
                    ('xc', W.DWORD), ('yc', W.DWORD), ('fill', W.DWORD), ('flags', W.DWORD),
                    ('show', W.WORD), ('reserved2size', W.WORD), ('reserved2', ptr),
                    ('stdin', W.HANDLE), ('stdout', W.HANDLE), ('stderr', W.HANDLE)]
    class SX(C.Structure):
        _fields_ = [('si', SI), ('attrs', ptr)]
    class PI(C.Structure):
        _fields_ = [('process', W.HANDLE), ('thread', W.HANDLE), ('pid', W.DWORD), ('tid', W.DWORD)]
    class SC(C.Structure):
        _fields_ = [('sid', ptr), ('caps', ptr), ('count', W.DWORD), ('reserved', W.DWORD)]
    class LIMIT(C.Structure):
        _fields_=[('per_process_time',C.c_int64),('per_job_time',C.c_int64),('flags',W.DWORD),
                  ('min_working',C.c_size_t),('max_working',C.c_size_t),('active',W.DWORD),
                  ('affinity',C.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
    class JOBLIMIT(C.Structure):
        _fields_=[('basic',LIMIT),('io',C.c_uint64*6),('process_memory',C.c_size_t),
                  ('job_memory',C.c_size_t),('peak_process',C.c_size_t),('peak_job',C.c_size_t)]
    for name, args, result in [
        ('InitializeProcThreadAttributeList', [ptr,W.DWORD,W.DWORD,C.POINTER(C.c_size_t)],W.BOOL),
        ('UpdateProcThreadAttribute',[ptr,W.DWORD,C.c_size_t,ptr,C.c_size_t,ptr,ptr],W.BOOL),
        ('DeleteProcThreadAttributeList',[ptr],None),
        ('CreateProcessW',[W.LPCWSTR,W.LPWSTR,ptr,ptr,W.BOOL,W.DWORD,ptr,W.LPCWSTR,ptr,ptr],W.BOOL),
        ('WaitForSingleObject',[W.HANDLE,W.DWORD],W.DWORD),
        ('GetExitCodeProcess',[W.HANDLE,C.POINTER(W.DWORD)],W.BOOL),
        ('TerminateProcess',[W.HANDLE,W.UINT],W.BOOL),
        ('CloseHandle',[W.HANDLE],W.BOOL),
        ('ResumeThread',[W.HANDLE],W.DWORD),
        ('CreateJobObjectW',[ptr,W.LPCWSTR],W.HANDLE),
        ('AssignProcessToJobObject',[W.HANDLE,W.HANDLE],W.BOOL),
        ('TerminateJobObject',[W.HANDLE,W.UINT],W.BOOL),
        ('SetInformationJobObject',[W.HANDLE,C.c_int,ptr,W.DWORD],W.BOOL),
    ]:
        f=getattr(k,name); f.argtypes=args; f.restype=result
    u.CreateAppContainerProfile.argtypes=[W.LPCWSTR,W.LPCWSTR,W.LPCWSTR,ptr,W.DWORD,C.POINTER(ptr)]
    u.CreateAppContainerProfile.restype=C.c_long
    u.DeleteAppContainerProfile.argtypes=[W.LPCWSTR]
    a.ConvertSidToStringSidW.argtypes=[ptr,C.POINTER(W.LPWSTR)]
    a.FreeSid.argtypes=[ptr]
    k.LocalFree.argtypes=[ptr]
    sid=ptr(); sid_text=W.LPWSTR(); attrs=None; pi=PI(); job=None
    profile='Beldin.Coding.'+uuid.uuid4().hex
    hr=u.CreateAppContainerProfile(profile,profile,'Temporary isolated Beldin test runner',None,0,C.byref(sid))
    if hr < 0:
        raise RuntimeError('Cannot create sandbox profile: '+hex(hr & 0xffffffff))
    if not a.ConvertSidToStringSidW(sid,C.byref(sid_text)):
        raise C.WinError(C.get_last_error())
    sid_string=sid_text.value
    grants=[]
    def acl(folder, right):
        p=subprocess.run([os.path.join(os.environ['SystemRoot'],'System32','icacls.exe'),str(folder),
                          '/grant', '*'+sid_string+':(OI)(CI)'+right],capture_output=True,
                         creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
        if p.returncode: raise RuntimeError('Sandbox ACL grant failed')
        grants.append(folder)
    try:
        acl(runtime,'RX'); acl(workspace,'M')
        for extra in (tool_dirs if tool else ()): acl(extra,'RX')
        size=C.c_size_t()
        k.InitializeProcThreadAttributeList(None,1,0,C.byref(size))
        attrs=C.create_string_buffer(size.value)
        if not k.InitializeProcThreadAttributeList(attrs,1,0,C.byref(size)): raise C.WinError(C.get_last_error())
        sc=SC(sid,None,0,0)
        if not k.UpdateProcThreadAttribute(attrs,0,0x20009,C.byref(sc),C.sizeof(sc),None,None): raise C.WinError(C.get_last_error())
        sx=SX(); sx.si.cb=C.sizeof(sx); sx.attrs=C.cast(attrs,ptr)
        # Output redirection is inside the sandbox, so no host handles are inherited.
        # AppContainer rewrites TEMP/TMP to its package-private AC\Temp even when
        # CreateProcess receives different values, so reset them inside the child
        # to the already ACL-granted disposable workspace.  Python tempfile creates
        # private directories with mode 0o700; on Windows that restrictive mode
        # conflicts with the AppContainer SID and fails with ERROR_ACCESS_DENIED.
        # Use inherited directory permissions for that mode only.  The AppContainer
        # and workspace ACL remain the security boundary.
        bootstrap="import os,runpy,sys;os.environ['TEMP']=os.getcwd();os.environ['TMP']=os.getcwd();_mkdir=os.mkdir;os.mkdir=lambda path,mode=0o777,*a,**kw:_mkdir(path,0o777 if mode==0o700 else mode,*a,**kw);sys.stdout=open('_stdout.txt','w',buffering=1);sys.stderr=open('_stderr.txt','w',buffering=1);sys.argv="+repr(argv)+";runpy.run_module(sys.argv.pop(0),run_name='__main__',alter_sys=True)"
        if tool:
            bootstrap=("import os,subprocess,sys;os.environ['TEMP']=os.getcwd();os.environ['TMP']=os.getcwd();"
                       "r=subprocess.run("+repr([str(tool),*argv])+",capture_output=True,text=True,timeout="+str(int(timeout))+",cwd=os.getcwd());"
                       "open('_stdout.txt','w',encoding='utf-8').write(r.stdout[-100000:]);open('_stderr.txt','w',encoding='utf-8').write(r.stderr[-100000:]);sys.exit(r.returncode)")
        command=C.create_unicode_buffer(subprocess.list2cmdline([str(runtime/'python.exe'),'-I','-B','-c',bootstrap]))
        env={'SystemRoot':os.environ['SystemRoot'],'WINDIR':os.environ['SystemRoot'],
             'USERPROFILE':os.environ.get('USERPROFILE',''),
             'LOCALAPPDATA':os.environ.get('LOCALAPPDATA',''),
             'TEMP':str(workspace),'TMP':str(workspace),
             'PATH':os.pathsep.join([str(runtime),*[str(d) for d in (tool_dirs if tool else ())]]),'PYTHONIOENCODING':'utf-8','BELDIN_CODING_SANDBOX':'1'}
        environment=C.create_unicode_buffer('\0'.join(k+'='+v for k,v in sorted(env.items()))+'\0\0')
        if not k.CreateProcessW(str(runtime/'python.exe'),command,None,None,False,
                                0x80000|0x400|0x08000000|4,environment,str(workspace),C.byref(sx),C.byref(pi)):
            raise C.WinError(C.get_last_error())
        job=k.CreateJobObjectW(None,None)
        limit=JOBLIMIT(); limit.basic.flags=0x2000|0x8|0x200; limit.basic.active=8; limit.job_memory=512*1024*1024
        if not job or not k.SetInformationJobObject(job,9,C.byref(limit),C.sizeof(limit)) or not k.AssignProcessToJobObject(job,pi.process): raise C.WinError(C.get_last_error())
        k.ResumeThread(pi.thread)
        start=time.monotonic(); status='completed'
        while k.WaitForSingleObject(pi.process,100)==258:
            if cancel and cancel.is_set(): status='cancelled'; break
            if time.monotonic()-start>timeout: status='timeout'; break
            if any(p.exists() and p.stat().st_size>131072 for p in (workspace/'_stdout.txt',workspace/'_stderr.txt')):
                status='output_limit'; break
        # Terminate descendants even when the initial process exits normally.
        code=W.DWORD(); k.GetExitCodeProcess(pi.process,C.byref(code))
        k.TerminateJobObject(job,1)
        k.WaitForSingleObject(pi.process,5000)
        def read(name):
            p=workspace/name
            if p.exists() and (p.is_symlink() or getattr(p.lstat(),'st_file_attributes',0)&0x400 or p.stat().st_nlink!=1):
                return '[unsafe output file rejected]'
            return p.read_bytes()[:32768].decode('utf-8','replace') if p.is_file() else ''
        return dict(status=status,exit_code=code.value if status=='completed' else None,
                    stdout=read('_stdout.txt'),stderr=read('_stderr.txt'),command=([str(tool.name),*argv] if tool else ['python','-m',*argv]))
    finally:
        if job: k.TerminateJobObject(job,1); k.CloseHandle(job)
        if pi.process:
            k.TerminateProcess(pi.process,1); k.CloseHandle(pi.process)
        if pi.thread: k.CloseHandle(pi.thread)
        if attrs: k.DeleteProcThreadAttributeList(attrs)
        for folder in reversed(grants):
            subprocess.run([os.path.join(os.environ['SystemRoot'],'System32','icacls.exe'),str(folder),'/remove:g','*'+sid_string],
                           capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
        k.LocalFree(sid_text); a.FreeSid(sid)
        u.DeleteAppContainerProfile(profile)
