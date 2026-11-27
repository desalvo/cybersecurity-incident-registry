#!/usr/bin/env python3
"""Decrypt an offline CIR statistics .enc.json file (password never on argv).

Usage: python scripts/decrypt_statistics_export.py data.enc.json data.xml
       python scripts/decrypt_statistics_export.py data.enc.json data.json --password-stdin
"""
import argparse
from getpass import getpass
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.statistics_visuals import decrypt_export


def main(argv=None):
    parser = argparse.ArgumentParser(description='Decrypt CIR AES-256-GCM statistics export')
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--password-stdin', action='store_true',
                        help='Read a single password line from stdin instead of prompting')
    args = parser.parse_args(argv)
    password = sys.stdin.readline().rstrip('\n') if args.password_stdin else getpass('Password for CIR export: ')
    try:
        plain = decrypt_export(args.source.read_bytes(), password)
    except Exception as exc:
        parser.exit(2, 'Decryption failed (wrong password or corrupted file).\n')
    # Refuse to overwrite existing files or create world-readable exports.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(args.destination), flags, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(plain)
    print('Decrypted export saved:', args.destination)


if __name__ == '__main__':
    main()
