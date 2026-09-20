"""Compare the delivered ZIP tree with the pinned base, including raw bytes.

Run before edits. Git status is authoritative for intended content; this also
detects line-ending-only packaging differences hidden by core.autocrlf.
"""
import json
import subprocess
from pathlib import Path

BASE="f3b442355b5035bb881ffe806580367ceebba820"
V1="02868bc10e735bda361d4f48d1300a569f85647b"


def git(*args): return subprocess.check_output(["git",*args])


def main():
    differences=[]
    for name in git("ls-tree","-r","--name-only",BASE).decode().splitlines():
        path=Path(name)
        base=git("show",f"{BASE}:{name}")
        current=path.read_bytes() if path.exists() else None
        if current!=base:
            kind="missing" if current is None else "line_endings_only" if current.replace(b"\r\n",b"\n")==base.replace(b"\r\n",b"\n") else "substantive"
            differences.append({"path":name,"kind":kind})
    result={"head":git("rev-parse","HEAD").decode().strip(),"branch":git("branch","--show-current").decode().strip(),
            "base":BASE,"v1_object_type":git("cat-file","-t",V1).decode().strip(),
            "git_status":git("status","--porcelain=v2","--untracked-files=all").decode(),
            "raw_byte_differences":differences}
    print(json.dumps(result,indent=2))


if __name__=="__main__": main()
