"""Independent diagnostic annotations added during review, separate from frozen raw scores.

No extractor import or extractor-generated expected label. Rules describe the
source text directly; these are metadata/semantic proxies rather than human
adjudication of every possible paraphrase.
"""
import json
from pathlib import Path
from eval.longitudinal_cases import WORLDS


def audit(directory):
    out=Path(directory)
    ingests=[json.loads(line) for line in (out/'ingestion.jsonl').read_text(encoding="utf8").splitlines()]
    memories={m['id']:m for m in json.loads((out/'memories.json').read_text(encoding="utf8"))}
    decisions=json.loads((out/'memory_decisions.json').read_text(encoding="utf8"))
    aliases=json.loads((out/'entity_aliases.json').read_text(encoding="utf8"))
    entities={e['id']:e for e in json.loads((out/'entities.json').read_text(encoding="utf8"))}
    checks=[]
    def emit(e,name,passed,observed):
        checks.append({'index':e['index'],'scenario':e['scenario'],'step':e['step'],'name':name,'passed':bool(passed),'observed':observed})
    for entry in ingests:
        w=entry['scenario'];step=entry['step']
        project,old,possible,new,activity,tool,issue=WORLDS[w]
        result=entry['result'].get('results',[{}])[0]
        iid=result.get('interaction_id')
        states=[]
        for decision in decisions:
            if decision['interaction_id']==iid and decision['action']!='expire':
                for state in json.loads(decision['new_state_json']):
                    states.append(dict(memories.get(state['id'],{}),**state))
        def text(m):return ' '.join(str(m.get(k,'')) for k in ('subject','value','canonical_text')).casefold()
        observed=[{k:m.get(k) for k in ('id','memory_type','subject','value','status','certainty','temporal_status','scope','subject_entity_id','value_entity_id')} for m in states]
        if step in {4,10,17,27}:
            month={4:11,10:12,17:1,27:1}[step]
            year=2026 if step in {4,10} else 2027
            iso=f'{year}-{month:02d}-{10+w:02d}'
            month_word={1:'january',11:'november',12:'december'}[month]
            def date_present(m):
                words=text(m)
                return iso in words or (month_word in words and str(10+w) in words and str(year) in words)
            passed=any(project.casefold() in text(m) and date_present(m) and m.get('status')=='active' and m.get('certainty')=='confirmed' and m.get('temporal_status')=='current' for m in states)
            emit(entry,'scheduled_date_is_current_knowledge',passed,observed)
        if step==6:
            def correct_scope(m):
                scope=m.get('scope','')
                fields=json.loads(scope) if scope.startswith('{') else {}
                return all(str(fields.get(k,'')).casefold()==v for k,v in {'app':'email','context':'work','project':project.casefold(),'recipient':'client'}.items())
            passed=any(m.get('memory_type')=='preference' and m.get('explicitness')=='explicit' and correct_scope(m) and any(word in text(m) for word in ('detailed','detail','thorough')) for m in states)
            emit(entry,'client_preference_keeps_all_restrictions',passed,observed)
        if step in {7,23}:
            passed=any(m.get('memory_type')=='episode' and str(m.get('subject','')).casefold()=='user' and project.casefold() in text(m) and issue.casefold() in text(m) for m in states)
            emit(entry,'first_person_action_is_user_episode',passed,observed)
        if step==8:
            passed=any(a['interaction_id']==iid and a['alias'].casefold()==(old+'Bee').casefold() and entities[a['entity_id']]['name'].casefold()==old.casefold() for a in aliases)
            emit(entry,'explicit_alias_has_source_certificate',passed,[a for a in aliases if a['interaction_id']==iid])
        if step==19:
            candidates=[m for m in memories.values() if project.casefold() in text(m) and 'alex' in text(m) and m.get('status')=='active']
            ids={m.get('subject_entity_id') for m in candidates if m.get('subject','').casefold()=='alex'}|{m.get('value_entity_id') for m in candidates if m.get('value','').casefold()=='alex'}
            qualifiers={entities[i]['qualifier'].casefold() for i in ids if i in entities}
            passed=any('museum' in q for q in qualifiers) and any('cycling' in q for q in qualifiers)
            emit(entry,'same_name_collaborators_preserve_two_identities',passed,[{'id':m['id'],'subject_entity_id':m.get('subject_entity_id'),'value_entity_id':m.get('value_entity_id')} for m in candidates])
    result={'annotation_stage':'independent diagnostic rules written during repository review, not the original frozen evaluation','passed':sum(c['passed'] for c in checks),'cases':len(checks),'categories':{name:{'passed':sum(c['passed'] for c in checks if c['name']==name),'cases':sum(c['name']==name for c in checks)} for name in sorted({c['name'] for c in checks})},'checks':checks,'limitations':['Literal source/entity/metadata proxies; valid unparsable paraphrases need human adjudication','Diagnostic rules are post hoc for the baseline and fixed before code replay','Collider identity check examines exported final identities; other checks use audited admission snapshots']}
    path=out/'semantic_diagnostics.json'
    if path.exists():raise ValueError('Do not overwrite diagnostic artifacts')
    path.write_text(json.dumps(result,indent=2),encoding='utf8')
    return {k:v for k,v in result.items() if k!='checks'}

if __name__=='__main__':
    import sys
    print(json.dumps(audit(sys.argv[1]),indent=2))
