# submodules/ — Shared modules linked via directory junctions
#
# This directory is populated by setup_junctions.bat (or generate.py link).
# Each subdirectory is a Windows junction pointing to blender_utils/submodules/<name>.
#
# DO NOT add this directory to .gitignore or .remoteignore.
# The publish script follows junctions and copies real files to the remote,
# ensuring the addon is self-contained on GitHub and in the extension zip.
