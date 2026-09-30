"""Human inspection of the same read-only packets used by the offline API."""
import html
import json
from pathlib import Path
import sys
from urllib.parse import urlencode

from datasette import hookimpl
from datasette.utils.asgi import Response
from markupsafe import Markup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ctw_adviser.queries import Queries, ResolutionError


def escape(value):
    return html.escape(str(value), quote=True)


def link(path, **params):
    return path + '?' + urlencode({k: v for k, v in params.items() if v is not None})


def raw(value):
    return '<pre>' + escape(json.dumps(value, indent=2, ensure_ascii=False)) + '</pre>'


def table(value):
    return '<table>' + ''.join('<tr><th>' + escape(k.replace('_', ' ')) + '</th><td>' +
                               escape('unknown' if v is None else json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) +
                               '</td></tr>' for k, v in value.items()) + '</table>'


def page(content, query=''):
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CTW · unit evidence inspection</title><style>
body{font:16px/1.5 system-ui,sans-serif;background:#f5f4f0;color:#172b3a;margin:0}main{max-width:1100px;margin:auto;padding:28px}
a{color:#155a79}h1{margin-bottom:4px}h2{font-size:1.35rem}h3{margin-bottom:6px}.preview{background:#f9e5bc;padding:10px 16px;border-radius:6px}
.card{background:white;border:1px solid #d5d9d8;border-radius:8px;padding:18px;margin:16px 0}input,select,button{font:inherit;padding:8px;border:1px solid #a7b5b9;border-radius:4px}
input{width:min(65%,520px)}button{background:#172b3a;color:white;cursor:pointer}table{border-collapse:collapse;width:100%;margin:12px 0}th,td{padding:7px 10px;border-bottom:1px solid #e5e8e7;text-align:left;vertical-align:top}th{width:30%;font-weight:500}
pre{font:13px/1.5 ui-monospace,monospace;overflow:auto;max-height:500px;background:#f1f4f4;padding:14px}summary{cursor:pointer}small,.muted{color:#52656e}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}.grid .card{margin:0}
</style><main><nav><a href="/inspect">Unit evidence</a> · <a href="/ctw/find_units?name=">Name search</a> · <a href="/ctw">All source tables</a> · <a href="https://github.com/OwenTanzer/CTW-adviser/pull/11">PR #11</a></nav>
<h1>Unit evidence inspection</h1><p class="preview">Phase 3 preview · PR #11 is unmerged. Independent code review completed; ready for inspection.</p>
<form action="/inspect"><input name="q" aria-label="Unit name or key" placeholder="Unit name or exact key" value="''' + escape(query) + '''"><button>Find unit</button></form>
<p class="muted">Base profiles and supported mechanics from pinned CTW-data. Conditional effects remain separate; no combat outcome is calculated.</p>''' + content + '</main></html>'


def unit_html(packet, args):
    unit = packet['units'][0]; identity = unit['identity']
    content = '<h2>' + escape(identity['name']) + '</h2><small>' + escape(identity['unit_key']) + '</small>'
    content += '<div class="grid"><section class="card"><h3>Identity & body</h3>' + table(identity) + table({k: v for k, v in unit['body'].items() if k != 'components'}) + '</section>'
    content += '<section class="card"><h3>Movement, leadership & cost</h3>' + table(unit['movement']) + table({'leadership': unit['leadership'], **unit['cost']}) + '<h3>Protection</h3>' + table(unit['passives']['protection']) + '</section></div>'
    for section, value in [('Components', unit['body']['components']), ('Melee attacks', unit['melee']), ('Ranged attacks', unit['ranged'])]:
        content += '<section class="card"><h3>' + section + '</h3>'
        if value is None:
            content += '<p>' + ('Known none.' if section.startswith('Ranged') else 'See section coverage below.') + '</p>'
        elif isinstance(value, list):
            content += ''.join(table({k: v for k, v in c.items() if k != 'provenance_refs'}) for c in value)
        else:
            primary = {k: v for k, v in value.items() if k not in ('variants', 'provenance_refs', 'native_parameters')}
            content += table(primary)
            if value.get('native_parameters'):
                content += '<details><summary>Source mechanical parameters</summary>' + table(value['native_parameters']) + '</details>'
            for variant in value.get('variants', []):
                content += '<details><summary>Additional attack: ' + escape(variant.get('projectile_key') or variant.get('weapon_key')) + '</summary>' + raw(variant) + '</details>'
        content += '</section>'
    content += '<section class="card"><h3>Attack traits & bonuses</h3>' + raw(unit['passives']['attack_traits']) + ''.join('<p><b>' + escape(k) + '</b>: ' + escape(v['summary']) + '</p>' for k, v in packet['trait_descriptions'].items()) + '</section>'
    content += '<section class="card"><h3>Attributes</h3>'
    for attribute in unit['passives']['attributes']:
        content += '<p><b>' + escape(attribute['name'] or attribute['key']) + '</b> — ' + escape(attribute['summary']) + '<br><small>' + escape(attribute['key']) + '</small></p>'
    content += '</section><section class="card"><h3>Core passives</h3>'
    for mechanic in unit['passives']['abilities']:
        content += '<article><h3>' + escape(mechanic['name'] or mechanic['key']) + '</h3><p>' + escape(mechanic['summary']) + '</p>'
        content += '<small>Culture: ' + escape(mechanic['culture_key']) + ' · requires effect enabling: ' + escape(mechanic['requires_effect_enabling']) + '</small>'
        content += '<details><summary>Effects, conditions & recipient phases</summary>' + raw({k: mechanic[k] for k in ('effects', 'conditions', 'phases', 'native_parameters', 'classification_evidence')}) + '</details>'
        content += '<a href="' + escape(link('/inspect/detail', ref=mechanic['detail_ref'])) + '">Full source evidence</a></article>'
    content += '</section><section class="card"><h3>Activated options</h3><p>Qualified listings; access and activity are not established by the link.</p>' + raw(unit['activated_options']) + '</section>'
    content += '<section class="card"><h3>Coverage & known gaps</h3>' + table({'melee': unit['coverage']['melee'], 'ranged': unit['coverage']['ranged']})
    for coverage in unit['coverage']['sections']:
        content += '<p><b>' + escape(coverage['name']) + '</b>: ' + escape(coverage['state']) + ' · returned ' + str(coverage['returned']) + ' of ' + str(coverage['total'])
        if coverage['cursor']:
            content += ' · <a href="' + escape(link('/inspect', **dict(args, section=coverage['name'], cursor=coverage['cursor'], mode=packet['mode']))) + '">Continue this section</a>'
        content += '</p>'
    content += '<details><summary>Development coverage notes (' + str(unit['coverage']['diagnostic_count']) + ')</summary>'
    content += ''.join('<p><b>' + escape(g['code']) + '</b>: ' + escape(g['summary']) + '</p>' for g in unit['coverage']['gaps']) + '</details></section>'
    content += '<section class="card"><h3>Provenance & detail</h3><p>Source commit ' + escape(packet['snapshot']['commit']) + ' · packet ' + escape(packet['schema_version']) + '</p>'
    content += '<details><summary>Source owners, locators and payload graph</summary>' + raw({k: packet[k] for k in ('snapshot', 'sources', 'provenance', 'payload_graph')}) + '</details>'
    content += '<details><summary>All detail links</summary><ul>' + ''.join('<li><a href="' + escape(link('/inspect/detail', ref=ref)) + '">' + escape(ref) + '</a></li>' for ref in packet['detail_refs']) + '</ul></details>'
    content += '<p><a href="' + escape(link('/inspect', **dict(args, format='json'))) + '">Download compact JSON packet</a> · <a href="' + escape(link('/inspect', **dict(args, format='json', diagnostics='1'))) + '">JSON with development notes</a></p></section>'
    return content


def database_path(datasette):
    return Path(datasette.get_database('ctw').path)


async def inspect(request, datasette):
    args = dict(request.args); query = args.get('unit') or args.get('q', '')
    try:
        with Queries(database_path(datasette)) as queries:
            if query:
                resolved = queries.resolve_unit(query, args.get('subculture'))
            else:
                resolved = {'status': 'not_found'}
            if resolved['status'] == 'resolved':
                packet = queries.get_unit_profile(resolved['resolved'], mode=args.get('mode', 'combined'),
                                                  section=args.get('section'), cursor=args.get('cursor'), limit=int(args.get('limit', '32')),
                                                  include_diagnostics=args.get('format') != 'json' or args.get('diagnostics') == '1')
                if args.get('format') == 'json':
                    return Response.json(packet)
                return Response.html(page(unit_html(packet, args), query))
            candidates = resolved.get('candidates', [])
            if not candidates:
                candidates = [dict(r) for r in queries.db.execute(
                    'SELECT unit_key,unit_name AS name,faction_name FROM unit_profiles WHERE unit_name LIKE ? ORDER BY unit_name,unit_key LIMIT 101',
                    ('%' + query + '%',))]
            content = '<section class="card"><h2>' + ('Choose a variant' if resolved['status'] == 'ambiguous' else 'Matching units') + '</h2><ul>'
            for candidate in candidates[:100]:
                content += '<li><a href="' + escape(link('/inspect', unit=candidate['unit_key'])) + '">' + escape(candidate['name']) + '</a> <small>' + escape(candidate['unit_key']) + '</small></li>'
            content += '</ul>' + ('<p>First 100 matches; refine the name to see others.</p>' if len(candidates) > 100 else '') + '</section>'
            return Response.html(page(content, query))
    except (ValueError, KeyError) as exc:
        return Response.html(page('<section class="card"><h2>Request could not be resolved</h2><p>' + escape(exc) + '</p></section>', query), status=400)


async def detail(request, datasette):
    args = dict(request.args)
    try:
        with Queries(database_path(datasette)) as queries:
            result = queries.get_detail(args.get('ref', ''), cursor=args.get('cursor'), limit=int(args.get('limit', '64')))
        if args.get('format') == 'json':
            return Response.json(result)
        content = '<section class="card"><h2>Source evidence detail</h2>' + raw(result)
        if result.get('cursor'):
            content += '<a href="' + escape(link('/inspect/detail', ref=args['ref'], cursor=result['cursor'], limit=args.get('limit', '64'))) + '">Continue evidence graph</a>'
        return Response.html(page(content + '</section>'))
    except (ValueError, KeyError) as exc:
        return Response.html(page('<p>' + escape(exc) + '</p>'), status=400)


@hookimpl
def register_routes(datasette):
    return [(r'^/inspect$', inspect), (r'^/inspect/detail$', detail)]


@hookimpl
def render_cell(row, value, column, table, database, datasette):
    if database == 'ctw' and column == 'unit_name' and value is not None:
        values = dict(row)
        return Markup('<a href="' + escape(link('/inspect', unit=values.get('unit_key'), q=None if values.get('unit_key') else value)) + '">' + escape(value) + '</a>')
