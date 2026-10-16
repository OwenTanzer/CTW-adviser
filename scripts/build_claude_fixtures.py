#!/usr/bin/env python3
"""Freeze Claude prompts and exact scenarios from the closed #6 receipts."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = Path('docs/evidence/closure-20261011/conversations')
CASES = [
    ('reiksguard', 3, '200m.cli.json', 'At 200 m, should Reiksguard approach a holding Doom Diver Catapult? Use unmodified ultra rank 0, flat unobstructed ground, 120 s.'),
    ('reiksguard', 4, '100m.cli.json', 'Change only the Reiksguard versus Doom Diver separation to 100 m. What changes?'),
    ('reiksguard', 5, '200m-delayed.cli.json', 'Return to the original 200 m scenario in case reiksguard-3. Change only Doom Diver flight delay to an illustrative 22.5 s. What changes?'),
    ('reiksguard', 6, '100m-delayed.cli.json', 'Return to the 100 m scenario in case reiksguard-4. Change only Doom Diver flight delay to the same illustrative 22.5 s. What changes?'),
    ('sea_guard', 3, 'front-cli.json', 'At 100 m, should shielded Lothern Sea Guard hold against approaching Blue Horrors, facing front? Use unmodified ultra rank 0, flat unobstructed ground, 120 s.'),
    ('sea_guard', 5, 'rear-cli.json', 'Change only the shielded Sea Guard facing to rear against the same Blue Horrors. What changes?'),
    ('bloodletters', 5, 'eight-contacts-cli.json', 'At 20 m, compare Bloodletters of Khorne and Kroxigor with eight active contacts per side. Use unmodified ultra rank 0, 120 s.'),
    ('bloodletters', 6, 'four-kroxigor-contacts-cli.json', 'Change only Kroxigor active contacts from eight to four. What changes?'),
    ('queen_bess', 4, 'cli_200m.json', 'At 200 m, should Queen Bess hold and fire at approaching Reiksguard? Use unmodified ultra rank 0, flat unobstructed ground, 120 s.'),
    ('queen_bess', 5, 'cli_300m.json', 'Change only Queen Bess versus Reiksguard separation to 300 m. What changes?'),
]


def main():
    cases = []
    for conversation, index, filename, prompt in CASES:
        path = BASE / conversation
        call = json.loads((ROOT / path / 'calls.json').read_text(encoding='utf-8'))[index]
        assert call.get('tool', call.get('name', '')).endswith('evaluate_single_unit_matchup')
        args = call['arguments']
        expected = json.loads((ROOT / path / filename).read_text(encoding='utf-8'))
        envelope = call['result'].get('value', call['result'])['structuredContent']
        assert envelope['status'] == 'ok' and expected == envelope['data']
        cases.append({'id': f'{conversation}-{index}', 'prompt': prompt,
                      'arguments': args, 'expected_result': (path / filename).as_posix(),
                      'expected_model_version': expected['model_version'],
                      'expected_source_commit': expected['snapshot']['commit']})
    manifest = {'workflow_version': '1.0.0', 'source': 'Closed issue #6 connected Work receipts',
                'cases': cases}
    target = ROOT / 'docs/claude-fixtures.json'
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'{target}: {len(cases)} cases')


if __name__ == '__main__':
    main()
