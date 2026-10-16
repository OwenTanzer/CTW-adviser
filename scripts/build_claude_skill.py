#!/usr/bin/env python3
"""Build a deterministic Claude Skills ZIP from the canonical CTW workflow."""

import argparse
from pathlib import Path
import re
import hashlib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/ctw-matchup/SKILL.md'
REFERENCE = ROOT / 'skills/ctw-matchup/references/calculation.md'


def build(output: Path) -> None:
    source = SKILL.read_text(encoding='utf-8')
    header = re.match(r'\A---\n(.*?)\n---\n', source, re.DOTALL)
    if not header:
        raise ValueError('Canonical skill lacks YAML frontmatter')
    description = ('Compare Total War Warhammer III unit matchups using the connected '
                   'CTW Advisor tools. Resolve units, inspect source evidence, evaluate '
                   'controlled scenarios, and give conditional tactical advice.')
    if len(description) > 200:
        raise ValueError('Claude skill description exceeds 200 characters')
    body = source[header.end():]
    body = body.replace('Prefer the installed CTW Advisor plugin.',
                        'Use the connected CTW Advisor custom connector.')
    body = body.replace('Canonical source: `OwenTanzer/CTW-adviser`, `skills/ctw-matchup/`. '
                        'Keep installed instructions synchronized; Claude adaptation '
                        'consumes this same workflow and shared server.',
                        'Canonical source: `OwenTanzer/CTW-adviser`, '
                        '`skills/ctw-matchup/`. This Claude skill is generated from that '
                        'workflow and uses the same shared server.')
    rendered = f'---\nname: ctw-matchup\ndescription: {description}\n---\n{body}'
    members = {
        'ctw-matchup/skill.md': rendered.encode('utf-8'),
        'ctw-matchup/references/calculation.md': REFERENCE.read_bytes(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(output) as archive:
        if archive.namelist() != list(members):
            raise ValueError('Unexpected Claude skill ZIP contents')
        for name, data in members.items():
            if archive.read(name) != data:
                raise ValueError(f'Corrupt Claude skill ZIP member: {name}')
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/ctw-matchup-claude-1.0.0.zip')
    build(parser.parse_args().output)
