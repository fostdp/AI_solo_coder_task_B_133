# -*- coding: utf-8 -*-
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

target = os.path.join(os.path.dirname(__file__), 'verify_imports.py')
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"

result = subprocess.run(
    [sys.executable, target],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    env=env,
    cwd=os.path.join(os.path.dirname(__file__), ".."),
)

output_file = os.path.join(os.path.dirname(__file__), "..", "verify_output.txt")
with open(output_file, "w", encoding="utf-8") as f:
    f.write("=== STDOUT ===\n")
    f.write(result.stdout or "")
    if result.stderr:
        f.write("\n=== STDERR ===\n")
        f.write(result.stderr)
    f.write(f"\n=== RETURN CODE: {result.returncode} ===\n")

print(open(output_file, encoding="utf-8").read())
sys.exit(result.returncode)
