import pytest
from app.services.answer_evidence import evidence_handles,map_answer
from app.services.answer_realization import realize_draft,requests_artifact
from tests.test_answer_evidence import record
from app.services.answer_evidence import necessary_evidence
from app.services.query_context import QueryPlan


@pytest.mark.parametrize('word,slot',[('materials','uses_material'),('standard','uses_standard')])
def test_explicit_slot_words_survive_draft_proposition_selection(word,slot):
    facts=[record('fact',predicate=slot,value='recorded value'),record('fact',predicate='deadline',value='January 10, 2027')]
    selected,_=necessary_evidence(f'Write our {word} and due date',QueryPlan(intent='draft'),facts,[])
    assert any(m['predicate']==slot for m in selected)


@pytest.mark.parametrize('query',['Summarize the equipment and due date in a message','Send a factual summary','Give the team a short briefing','Brief FelixBee about materials and due date'])
def test_explicit_artifact_request_cannot_be_misclassified_as_plain_question(query):
    assert requests_artifact(query)


@pytest.mark.parametrize('query',['What equipment do we use?','Give me the current coordinator','Summarize the evidence'])
def test_plain_question_or_underspecified_summary_is_not_forced_to_draft(query):
    assert not requests_artifact(query)


def test_draft_route_does_not_call_free_prose_generator(monkeypatch):
    from tests.test_memory_lifecycle import db_session
    from tests.test_v2_behavior import learn
    from app.services.hey_kivi import answer_query
    from app.services import hey_kivi
    db=db_session();learn(db,monkeypatch,'Cedar Archive uses TIFF.','TIFF',subject='Cedar Archive',predicate='uses',memory_type='fact',canonical_text='Cedar Archive uses TIFF.',scope={'project':'cedar archive'})
    def chat(system,user,schema,name):
        if name=='query_plan':return ({'intent':'draft','entities':['Cedar Archive'],'predicates':['uses']},{})
        if name=='evidence_verdict':return ({'supported':True,'reason':'Exact structured proposition matches the evidence.'},{})
        raise AssertionError('draft free-prose generator was called')
    monkeypatch.setattr(hey_kivi.provider,'enabled',True);monkeypatch.setattr(hey_kivi.provider,'chat_json',chat)
    result=answer_query(db,'Write a Cedar Archive tool update.','s')
    assert 'Cedar Archive uses TIFF.' in result['response']
    assert result['model_usage']['generation']['model']=='deterministic_structured_realizer'


def test_same_model_verifier_cannot_veto_exact_structured_proposition(monkeypatch):
    from tests.test_memory_lifecycle import db_session
    from tests.test_v2_behavior import learn
    from app.services.hey_kivi import answer_query
    from app.services import hey_kivi
    db=db_session();learn(db,monkeypatch,'Cedar Archive uses TIFF.','TIFF',subject='Cedar Archive',predicate='format',memory_type='fact',canonical_text='Cedar Archive uses TIFF.',scope={'project':'cedar archive'})
    def chat(system,user,schema,name):
        if name=='query_plan':return ({'intent':'draft','entities':['Cedar Archive'],'predicates':['format']},{})
        if name=='evidence_verdict':return ({'supported':False,'reason':'Stochastic category disagreement.'},{})
        raise AssertionError('draft free-prose generator was called')
    monkeypatch.setattr(hey_kivi.provider,'enabled',True);monkeypatch.setattr(hey_kivi.provider,'chat_json',chat)
    result=answer_query(db,'Compose a Cedar Archive format note.','s')
    assert result['response']=='The format for Cedar Archive is TIFF.'
    assert result['model_usage']['verdict']['supported'] is False
    assert result['model_usage']['verification_authority']=='diagnostic_only_for_structured_realization'


def test_diagnostic_verifier_timeout_cannot_veto_exact_structured_proposition(monkeypatch):
    from tests.test_memory_lifecycle import db_session
    from tests.test_v2_behavior import learn
    from app.services.hey_kivi import answer_query
    from app.services import hey_kivi
    db=db_session();learn(db,monkeypatch,'Coral Survey uses sonar.','sonar',subject='Coral Survey',predicate='uses',memory_type='fact',canonical_text='Coral Survey uses sonar.',scope={'project':'coral survey'})
    def chat(system,user,schema,name):
        if name=='query_plan':return ({'intent':'draft','entities':['Coral Survey'],'predicates':['uses']},{})
        if name=='evidence_verdict':raise TimeoutError('timed out')
        raise AssertionError('draft free-prose generator was called')
    monkeypatch.setattr(hey_kivi.provider,'enabled',True);monkeypatch.setattr(hey_kivi.provider,'chat_json',chat)
    result=answer_query(db,'Give the Coral Survey team a short briefing about sonar.','s')
    assert result['response']=='Coral Survey uses sonar.'
    assert result['model_usage']['verification_authority']=='diagnostic_only_for_structured_realization'
    assert any(e['component']=='evidence_verifier' for e in result['model_usage']['retrieval_errors'])


@pytest.mark.parametrize('slot,value,forbidden',[
    ('uses','TIFF','all assets'),('deadline','January 10, 2027','must deliver'),
    ('uses_material','oak panels','will utilize'),('coordinator','Tessa','everything'),
    ('uses_standard','Dublin Core','equipment'),('purpose','ticketing','optimize')])
def test_realization_preserves_semantic_content(slot,value,forbidden):
    _,mapping=evidence_handles([record('fact',subject='Example project',predicate=slot,value=value)],[])
    result,props=realize_draft('Draft an update',mapping)
    assert value in result['answer'] and forbidden not in result['answer']
    assert props[0]['predicate']==slot
    assert map_answer(result,mapping)['used_memory_ids']


@pytest.mark.parametrize('query',['Write equipment and delivery timing','Compose a tool and due date briefing','Draft the format and deadline note'])
def test_unnecessary_coordinator_excluded_from_faceted_artifact(query):
    _,mapping=evidence_handles([record('fact',predicate='uses',value='sonar'),record('relationship',predicate='coordinator',value='Alma')],[])
    result,_=realize_draft(query,mapping)
    assert 'sonar' in result['answer'] and 'Alma' not in result['answer']


@pytest.mark.parametrize('style',['warmer','detailed','concise','direct','bullet points'])
def test_preferences_change_presentation_without_becoming_fact_sentences(style):
    facts=[record('fact',predicate='uses_material',value='oak panels'),record('fact',predicate='deadline',value='January 15, 2027',memory_id=2)]
    _,plain=evidence_handles(facts,[])
    _,styled=evidence_handles(facts+[record('preference',predicate='email_style',value=style,memory_id=3)],[])
    base,_=realize_draft('Draft a project update',plain);result,_=realize_draft('Draft a project update',styled)
    assert result['applied_preferences']==['E3']
    assert result['claims']==base['claims']
    assert 'prefer' not in result['answer'] and style not in result['answer']
    if style=='warmer':assert result['answer'].startswith('Hello,') and result['answer'].endswith('Thank you!')
    if style=='detailed':assert 'Project update' in result['answer'] and '- ' in result['answer']
    if style=='concise':assert len(result['answer'])<len(base['answer'])
    if style=='direct':assert result['answer']==base['answer'] # direct factual defaults
    if style=='bullet points':assert result['answer'].startswith('- ')


@pytest.mark.parametrize('state,certainty',[('historical','confirmed'),('future','tentative'),('current','reported')])
def test_nonconfirmed_or_noncurrent_proposition_stays_dated_quote(state,certainty):
    r=record('fact',predicate='uses_material',value='oak panels',temporal_status=state,certainty=certainty)
    r['source_evidence'][0]['excerpt']='We might use oak panels.'
    _,mapping=evidence_handles([r],[]);result,_=realize_draft('Draft an update',mapping)
    assert 'Recorded on' in result['answer'] and 'might' in result['answer']
    assert 'uses oak panels' not in result['answer']
