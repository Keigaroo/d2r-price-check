"""Updater for the zip/Setup.bat install (run by 'Start Price Check.bat' before the program).

Checks the latest GitHub release; if it is newer than this copy, downloads that release's source
and replaces the program files in the d2pc folder (settings, cache and captures are kept).
Run:  python -m d2pc.update_source
"""
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ver(tag):
    return tuple(int(x) for x in re.findall(r"\d+", tag or "")[:3]) or (0,)


def main():
    from .version import GITHUB_REPO, __version__
    if not GITHUB_REPO:
        return 0
    if os.path.isdir(os.path.join(APP_DIR, ".git")):
        print("Developer copy (git) - skipping auto-update.")
        return 0
    try:
        import requests
        r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                         headers={"Accept": "application/vnd.github+json"}, timeout=8)
        if r.status_code != 200:
            return 0
        tag = r.json().get("tag_name", "")
    except Exception as e:
        print(f"Update check skipped ({e}).")
        return 0
    if _ver(tag) <= _ver(__version__):
        print(f"D2R Price Check v{__version__} is up to date.")
        return 0

    print(f"Updating D2R Price Check v{__version__} -> {tag} ...")
    try:
        z = requests.get(f"https://github.com/{GITHUB_REPO}/archive/refs/tags/{tag}.zip", timeout=60)
        z.raise_for_status()
        zf = zipfile.ZipFile(io.BytesIO(z.content))
        root = zf.namelist()[0].split("/")[0] + "/"
        names = [n for n in zf.namelist() if n.startswith(root + "d2pc/") and not n.endswith("/")]
        if not any(n.endswith("d2pc/main.py") for n in names):
            raise IOError("release archive has no program files")
        old_req = open(os.path.join(APP_DIR, "requirements.txt"), encoding="utf-8").read() \
            if os.path.exists(os.path.join(APP_DIR, "requirements.txt")) else ""
        # Unpack to a temporary folder first, then swap, so a failed download never leaves half a program.
        tmp = os.path.join(APP_DIR, "d2pc.new")
        shutil.rmtree(tmp, ignore_errors=True)
        for n in names:
            dest = os.path.join(tmp, n[len(root) + len("d2pc/"):])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(zf.read(n))
        live = os.path.join(APP_DIR, "d2pc")
        backup = os.path.join(APP_DIR, "d2pc.old")
        shutil.rmtree(backup, ignore_errors=True)
        os.replace(live, backup)
        os.replace(tmp, live)
        shutil.rmtree(backup, ignore_errors=True)
        for extra in ("requirements.txt", "READ ME FIRST.txt", "README.md"):
            n = root + extra
            if n in zf.namelist():
                with open(os.path.join(APP_DIR, extra), "wb") as f:
                    f.write(zf.read(n))
        new_req = zf.read(root + "requirements.txt").decode("utf-8") if root + "requirements.txt" in zf.namelist() else old_req
        if new_req != old_req:
            print("Installing new required packages...")
            subprocess.call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q",
                             "-r", os.path.join(APP_DIR, "requirements.txt")])
        print(f"Updated to {tag}.")
    except Exception as e:
        print(f"Update failed, keeping the current version: {e}")
        live = os.path.join(APP_DIR, "d2pc")
        backup = os.path.join(APP_DIR, "d2pc.old")
        if not os.path.isdir(live) and os.path.isdir(backup):
            os.replace(backup, live)
    return 0


if __name__ == "__main__":
    sys.exit(main())
