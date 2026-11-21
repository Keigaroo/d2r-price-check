"""Self-update for the .exe build.

On start-up the program asks GitHub for the latest release. If it is newer, the new .exe is
downloaded next to the current one and swapped in:
  D2RPriceCheck.exe      -> renamed to D2RPriceCheck.exe.old (Windows allows renaming a running exe)
  D2RPriceCheck.exe.new  -> renamed to D2RPriceCheck.exe
The new version is then started and the old one exits. The .old file is deleted on the next start.
Nothing happens when running from source (python -m d2pc.main) or when GITHUB_REPO is empty.
"""
import os
import re
import subprocess
import sys

from .version import EXE_ASSET_NAME, GITHUB_REPO, __version__


def _ver(tag):
    return tuple(int(x) for x in re.findall(r"\d+", tag or "")[:3]) or (0,)


def is_frozen():
    return getattr(sys, "frozen", False)


def cleanup_old():
    if not is_frozen():
        return
    old = sys.executable + ".old"
    try:
        if os.path.exists(old):
            os.remove(old)
    except OSError:
        pass


def check(log=print):
    """Returns (latest_tag, download_url) if a newer release exists, else None."""
    if not GITHUB_REPO:
        return None
    import requests
    try:
        r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                         headers={"Accept": "application/vnd.github+json"}, timeout=8)
        if r.status_code != 200:
            return None
        rel = r.json()
    except Exception as e:
        log(f"Update check failed: {e}")
        return None
    tag = rel.get("tag_name", "")
    if _ver(tag) <= _ver(__version__):
        return None
    for a in rel.get("assets", []):
        if a.get("name") == EXE_ASSET_NAME:
            return tag, a["browser_download_url"]
    return None


def apply(tag, url, log=print):
    """Download and swap in the new exe, then restart. Returns False if it couldn't."""
    if not is_frozen():
        log(f"Version {tag} is available (running from source: update with git/zip instead).")
        return False
    import requests
    exe = sys.executable
    new, old = exe + ".new", exe + ".old"
    log(f"Downloading update {tag}...")
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(new, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
        if os.path.getsize(new) < 1_000_000:
            raise IOError("downloaded file is too small")
        if os.path.exists(old):
            os.remove(old)
        os.replace(exe, old)
        os.replace(new, exe)
    except Exception as e:
        log(f"Update failed, keeping the current version: {e}")
        try:
            if not os.path.exists(exe) and os.path.exists(old):
                os.replace(old, exe)
            if os.path.exists(new):
                os.remove(new)
        except OSError:
            pass
        return False
    log(f"Updated to {tag}. Restarting...")
    subprocess.Popen([exe] + sys.argv[1:], cwd=os.path.dirname(exe))
    return True
