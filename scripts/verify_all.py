"""One-command offline verification: unit suites plus the demo evaluation kit.

  python scripts/verify_all.py

Exits 0 only if every check passes. No RPC, HTTP, or external data.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(label, command):
    result = subprocess.run([sys.executable, *command], cwd=ROOT,
                            capture_output=True, text=True)
    status = 'PASS' if result.returncode == 0 else 'FAIL'
    print(f'{label}: {status}')
    if result.returncode != 0:
        print((result.stdout + result.stderr)[-2000:])
    return result.returncode == 0


def main():
    checks = [
        run('unit tests', ['-m', 'unittest', 'discover', '-q']),
        run('demo kit', ['scripts/demo_reputation.py']),
    ]
    print('VERIFY ALL PASS' if all(checks) else 'VERIFY ALL FAIL')
    return 0 if all(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
