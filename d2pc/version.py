"""Version number and where updates are published.

Releases are published on GitHub. Each release has a tag like v1.2.0 and a
D2RPriceCheck.exe file attached; the program compares its own version to the latest one.
"""
__version__ = "1.2.2"

# "owner/repository" on GitHub. Filled in once the repository exists.
GITHUB_REPO = "Keigaroo/d2r-price-check"
EXE_ASSET_NAME = "D2RPriceCheck.exe"

# Changing __version__ and pushing to main publishes a new release automatically.
