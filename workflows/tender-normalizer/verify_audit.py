"""Verify downloaded tender AUDIT and dataset JSON; no network or third-party deps."""
import argparse
import hashlib
import json
from pathlib import Path


def json_numbers(value):
    """Preserve object order, normalizing only integral JSON floating-point values."""
    if isinstance(value, dict):
        return {key: json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_numbers(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def checksum(value):
    """Match auditVersion 1.0.0's ordered, finite JSON encoding."""
    encoded = json.dumps(json_numbers(value), sort_keys=False, ensure_ascii=False,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--input-records', type=Path, help='Selected parsed row array, not full Actor input')
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding='utf-8'))
    dataset = json.loads(args.dataset.read_text(encoding='utf-8'))
    if audit.get('auditVersion') != '1.0.0':
        raise ValueError('unsupported auditVersion')
    checks = {'delivered': checksum(dataset) == audit['deliveredSha256'],
              'settings': checksum(audit['settings']) == audit['settingsSha256'],
              'rowsDelivered': len(dataset) == audit['rowsDelivered']}
    if args.input_records:
        records = json.loads(args.input_records.read_text(encoding='utf-8'))
        checks['input'] = checksum(records) == audit['inputSha256']
        checks['rowsReceived'] = len(records) == audit['rowsReceived']
    print(json.dumps({'checks': checks, 'sourceAuthenticity': 'UNVERIFIED'}))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
