"""Fixed local services, normal-user login task. No command or network inputs."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
OLLAMA=Path(r"C:\Users\BELDIN_USER\AppData\Local\Programs\Ollama\ollama.exe")

def listening(port):
    try:
        with socket.create_connection(("127.0.0.1",port),timeout=1): return True
    except OSError: return False

def main():
    if not OLLAMA.is_file(): raise RuntimeError("Ollama executable unavailable")
    children={}
    retry={}
    while True:
        for port,args in ((8765,[sys.executable,"-B","-m","beldin.server"]),
                          (11434,[str(OLLAMA),"serve"])):
            child=children.get(port)
            if child is not None and child.poll() is None: continue
            if listening(port) or time.monotonic()<retry.get(port,0): continue
            env=os.environ.copy()
            env["OLLAMA_HOST"]="127.0.0.1:11434"
            env.pop("BELDIN_TOKEN",None)
            try:
                children[port]=subprocess.Popen(args,cwd=ROOT,env=env,
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            except OSError: pass
            retry[port]=time.monotonic()+30
        time.sleep(5)

if __name__=="__main__": main()
