from datetime import datetime,timedelta
import json
from sqlalchemy import select
from tests.test_memory_lifecycle import db_session,interaction,candidate,run_with
from app.models import Memory,MemoryDecision,ForgetBoundary,Entity
from app.services.lifecycle import reconcile,expire,safe_evidence
from app.services.retrieval import retrieve_memories,retrieve_history,vector_scores
from app.services.query_context import QueryPlan,scope_matches,plan_query
from app.services.entities import lookup
from app.services import memory_engine,hey_kivi


def learn(db,monkeypatch,text,value,day=0,**fields):
    row=interaction(db,text,datetime(2026,9,1)+timedelta(days=day));c=candidate(value);c.update(fields)
    run_with(db,monkeypatch,row,c);return row


def test_tentative_future_never_overwrites_current(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Rajeev is my manager.","Rajeev")
    learn(db,monkeypatch,"Priya might become my manager.","Priya",1,certainty="tentative",temporal_status="future")
    assert [(m.value,m.status) for m in db.scalars(select(Memory))]==[("Rajeev","active"),("Priya","tentative")]
    ranked,_=retrieve_memories(db,"Who is my manager?",plan=QueryPlan(predicates=["manager"]))
    assert [m.value for m,_ in ranked]==["Rajeev"]


def test_confirmation_promotes_and_closes_previous(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Rajeev is my manager.","Rajeev")
    learn(db,monkeypatch,"Priya might become my manager.","Priya",1,certainty="tentative",temporal_status="future")
    learn(db,monkeypatch,"Priya officially became my manager.","Priya",2,change_kind="replace")
    rows=list(db.scalars(select(Memory)));assert len(rows)==2
    assert [(m.value,m.status) for m in rows]==[("Rajeev","superseded"),("Priya","active")]
    assert rows[1].canonical_text=="manager: Priya"
    assert rows[1].expires_at is None
    decisions=list(db.scalars(select(MemoryDecision)));assert json.loads(decisions[-1].previous_state_json)
    assert json.loads(decisions[-1].new_state_json)[-1]["certainty"]=="confirmed"


def test_forget_blocks_unpromoted_paraphrase_and_history(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Rajeev is my manager.","Rajeev")
    interaction(db,"I report to Rajeev at work.",datetime(2026,9,1,3))
    learn(db,monkeypatch,"Forget who my manager is.","any",2,proposed_action="delete")
    assert retrieve_memories(db,"Who is my manager?",plan=QueryPlan())[0]==[]
    assert retrieve_history(db,"Who did I report to?",plan=QueryPlan(intent="historical"))==[]
    assert db.scalars(select(ForgetBoundary)).one()
    learn(db,monkeypatch,"Ananya is my manager.","Ananya",3)
    assert [m.value for m,_ in retrieve_memories(db,"Who is my manager?",plan=QueryPlan(predicates=["manager"]))[0]]==["Ananya"]


def test_forget_without_promoted_memory_still_installs_boundary(monkeypatch):
    db=db_session();interaction(db,"I report to Rajeev.",datetime(2026,9,1))
    learn(db,monkeypatch,"Forget my manager.","any",2,proposed_action="delete")
    assert retrieve_history(db,"Rajeev",plan=QueryPlan(intent="historical"))==[]


def test_nonretention_never_enters_history(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Don't remember this, room is 804.","804",predicate="room")
    assert not list(db.scalars(select(Memory)))
    assert retrieve_history(db,"room",plan=QueryPlan(intent="historical"))==[]


def test_missing_or_fabricated_evidence_rejected(monkeypatch):
    db=db_session();row=interaction(db,"Thanks.",datetime(2026,9,1));c=candidate("Rajeev");c["evidence_text"]="Rajeev is my manager."
    monkeypatch.setattr(memory_engine,"extract_candidates",lambda *_:([c],{},[]))
    assert memory_engine.process_interaction(db,row)["actions"][0]["action"]=="ignore"
    assert not list(db.scalars(select(Memory)))


def test_fabricated_delete_evidence_cannot_install_boundary(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Rajeev is my manager.","Rajeev")
    row=interaction(db,"Thanks.",datetime(2026,9,2))
    c=candidate("any");c.update(proposed_action="delete",evidence_text="Forget my manager.")
    monkeypatch.setattr(memory_engine,"extract_candidates",lambda *_:([c],{},[]))
    assert memory_engine.process_interaction(db,row)["actions"][0]["action"]=="ignore"
    assert db.scalars(select(Memory)).one().status=="active"
    assert not list(db.scalars(select(ForgetBoundary)))


def test_low_confidence_delete_cannot_install_boundary(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Rajeev is my manager.","Rajeev")
    row=interaction(db,"Forget my manager.",datetime(2026,9,2))
    c=candidate("any");c.update(proposed_action="delete",confidence=.2,evidence_text=row.formatted_text)
    monkeypatch.setattr(memory_engine,"extract_candidates",lambda *_:([c],{},[]))
    assert memory_engine.process_interaction(db,row)["actions"][0]["action"]=="clarify"
    assert db.scalars(select(Memory)).one().status=="active"
    assert not list(db.scalars(select(ForgetBoundary)))


def test_alias_and_same_name_collision(monkeypatch):
    db=db_session()
    learn(db,monkeypatch,"Aaditya, also called Aadi, reviews Atlas.","Atlas",predicate="reviews",subject="Aaditya",
          entities=[{"name":"Aaditya","kind":"person","qualifier":"","aliases":["Aadi"],"evidence_text":"Aaditya, also called Aadi, reviews Atlas."}])
    assert lookup(db,"Aadi")[0].name=="Aaditya"
    for qualifier in ["college","work"]:
        learn(db,monkeypatch,f"Rahul from {qualifier} reviews my work.","user",subject="Rahul",subject_qualifier=qualifier,predicate="reviews",cardinality="multi")
    assert len(lookup(db,"Rahul"))==2
    plan,_,_=plan_query(db,"Write Rahul an update")
    assert plan.clarification


def test_fact_object_admitted_later_is_retrievable(monkeypatch):
    db=db_session()
    learn(db,monkeypatch,"Leela organizes ceramics exhibition.","ceramics exhibition",
          subject="Leela",predicate="organizes",memory_type="fact",cardinality="multi")
    learn(db,monkeypatch,"ceramics exhibition needs stoneware labels.","stoneware labels",1,
          subject="ceramics exhibition",predicate="needs",memory_type="fact")
    entity=lookup(db,"ceramics exhibition")[0]
    ranked,_=retrieve_memories(db,"Who organizes ceramics exhibition?",
        plan=QueryPlan(predicates=["organizes"]),entity_ids={entity.id})
    assert [m.subject for m,_ in ranked]==["Leela"]


def test_unlinked_same_name_object_does_not_choose_identity(monkeypatch):
    db=db_session()
    learn(db,monkeypatch,"Atlas involves Alex.","Alex",subject="Atlas",predicate="involves",memory_type="fact")
    for day,qualifier in enumerate(["museum","cycling"],1):
        learn(db,monkeypatch,f"Alex from {qualifier} reviews exhibits.","exhibits",day,
              subject="Alex",subject_qualifier=qualifier,predicate="reviews",cardinality="multi")
    entities=lookup(db,"Alex")
    assert len(entities)==2
    ranked,_=retrieve_memories(db,"What involves Alex?",plan=QueryPlan(predicates=["involves"]),entity_ids={entities[0].id})
    assert ranked==[]


def test_forget_resolves_explicit_subject_alias(monkeypatch):
    db=db_session();text="Aaditya, also called Aadi, reviews Atlas."
    learn(db,monkeypatch,text,"Atlas",subject="Aaditya",predicate="review_responsibility",
          entities=[{"name":"Aaditya","kind":"person","qualifier":"","aliases":["Aadi"],"evidence_text":text}])
    learn(db,monkeypatch,"Forget Aadi's review responsibilities.","any",1,
          subject="Aadi",predicate="review_responsibility",proposed_action="delete")
    assert db.scalars(select(Memory)).one().status=="deleted"
    assert retrieve_memories(db,"Aadi reviews Atlas",plan=QueryPlan(predicates=["review_responsibility"]))[0]==[]


def test_qualified_subject_forget_preserves_other_identity(monkeypatch):
    db=db_session()
    for day,qualifier in enumerate(["museum","cycling"]):
        text=f"Alex from {qualifier} reviews Atlas."
        learn(db,monkeypatch,text,"Atlas",day,subject="Alex",subject_qualifier=qualifier,
              predicate="review_responsibility",canonical_text=text)
    learn(db,monkeypatch,"Forget Alex from museum's review responsibilities.","any",3,
          subject="Alex",subject_qualifier="museum",predicate="review_responsibility",proposed_action="delete")
    rows=list(db.scalars(select(Memory)))
    assert [m.status for m in rows]==["deleted","active"]
    cycle=lookup(db,"Alex","cycling")[0]
    ranked,_=retrieve_memories(db,"Alex reviews Atlas",plan=QueryPlan(predicates=["review_responsibility"]),entity_ids={cycle.id})
    assert [m.id for m,_ in ranked]==[rows[1].id]
    assert safe_evidence(db,rows[1],rows[1].sources[0])=="Alex from cycling reviews Atlas."


def test_same_named_qualified_objects_are_distinct(monkeypatch):
    db=db_session()
    for day,qualifier in enumerate(["museum","cycling"]):
        text=f"Alex from {qualifier} collaborates on Atlas."
        learn(db,monkeypatch,text,"Alex",day,subject="Atlas",value_qualifier=qualifier,
              predicate="collaborator",cardinality="multi",canonical_text=text)
    rows=list(db.scalars(select(Memory)))
    assert len(rows)==2
    assert rows[0].value_entity_id!=rows[1].value_entity_id
    assert [len(m.sources) for m in rows]==[1,1]


def test_forget_one_qualified_object_preserves_other(monkeypatch):
    db=db_session()
    for day,qualifier in enumerate(["museum","cycling"]):
        text=f"Alex from {qualifier} collaborates on Atlas."
        learn(db,monkeypatch,text,"Alex",day,subject="Atlas",value_qualifier=qualifier,
              predicate="collaborator",cardinality="multi",canonical_text=text)
    learn(db,monkeypatch,"Forget Alex from museum as collaborator on Atlas.","Alex",3,
          subject="Atlas",value_qualifier="museum",predicate="collaborator",cardinality="multi",proposed_action="delete")
    rows=list(db.scalars(select(Memory)))
    assert [m.status for m in rows]==["deleted","active"]
    assert safe_evidence(db,rows[1],rows[1].sources[0])=="Alex from cycling collaborates on Atlas."


def test_inferred_preferences_need_independent_observations(monkeypatch):
    db=db_session()
    for day in [0,0,1]:
        learn(db,monkeypatch,"Make this work email shorter.","concise",day,memory_type="preference",predicate="communication_length",explicitness="inferred",scope={"app":"email","context":"work"})
    memories=list(db.scalars(select(Memory)));assert len(memories)==1 and memories[0].status=="active"
    assert memories[0].confidence<=0.85 and len(memories[0].sources)==3
    plan=QueryPlan(intent="draft",app="whatsapp",context="personal")
    assert retrieve_memories(db,"Draft update",plan=plan)[0]==[]


def test_inferred_conflicts_do_not_promote(monkeypatch):
    db=db_session()
    for day,value in enumerate(["concise","detailed","concise","concise"]):
        learn(db,monkeypatch,f"Make email {value}.",value,day,memory_type="preference",predicate="length",explicitness="inferred",scope={"app":"email"})
    assert all(m.status=="pending" for m in db.scalars(select(Memory)))


def test_narrow_scope_and_explicit_preference_win(monkeypatch):
    db=db_session()
    learn(db,monkeypatch,"Keep work updates short.","concise",memory_type="preference",predicate="length",scope={"context":"work"})
    learn(db,monkeypatch,"For client emails I prefer detail.","detailed",1,memory_type="preference",predicate="length",scope={"context":"work","app":"email","recipient":"client"})
    ranked,_=retrieve_memories(db,"Draft email update",plan=QueryPlan(intent="draft",context="work",app="email",recipient="client"))
    assert [m.value for m,_ in ranked]==["detailed"]
    assert not scope_matches('{"context":"work"}',QueryPlan(context="personal"))


def test_expiration_and_historical_retrieval(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Workshop is this week.","workshop",memory_type="episode",predicate="event",valid_until="2026-09-04T00:00:00")
    expire(db,datetime(2026,9,5));assert db.scalars(select(Memory)).one().status=="expired"
    assert retrieve_memories(db,"Workshop",plan=QueryPlan(),now=datetime(2026,9,5))[0]==[]
    assert retrieve_memories(db,"Workshop",plan=QueryPlan(intent="historical"),now=datetime(2026,9,5))[0]


def test_time_app_episode_constraints():
    db=db_session()
    for app,hour in [("Slack",17),("Slack",10),("Gmail",17)]:
        row=interaction(db,"Auth middleware rejected refreshed tokens.",datetime(2026,9,15,hour));row.app_context=app;db.commit()
    plan,ids,_=plan_query(db,"Find dictation around 5 PM yesterday in Slack",now=datetime(2026,9,16,9))
    rows=retrieve_history(db,"Find dictation",plan=plan,entity_ids=ids)
    assert len(rows)==1 and rows[0][0].occurred_at.hour==17 and rows[0][0].app_context=="Slack"


def test_embedding_error_visible_and_model_tag_rebuild(monkeypatch):
    db=db_session();row=interaction(db,"A login failure.",datetime(2026,9,1));row.embedding_json="[1,0]";row.embedding_model="old"
    monkeypatch.setattr(memory_engine.provider,"enabled",True)
    calls=[]
    def embed(texts): calls.append(texts);return [[1,0] for _ in texts]
    monkeypatch.setattr(memory_engine.provider,"embed",embed);errors=[]
    assert vector_scores(db,"authentication",[row],[row.formatted_text],errors)==[1.0]
    assert len(calls)==2 and row.embedding_model!="old"
    monkeypatch.setattr(memory_engine.provider,"embed",lambda *_: (_ for _ in ()).throw(ValueError("unavailable")))
    assert vector_scores(db,"authentication",[row],[row.formatted_text],errors)==[0.0]
    assert errors[-1]["fallback"]=="lexical"


def test_auth_debugging_episode_is_not_a_secret(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Auth middleware invalidates refreshed tokens.","refreshed token invalidation",memory_type="episode",predicate="auth_issue")
    assert db.scalars(select(Memory)).one().value=="refreshed token invalidation"
    assert not memory_engine._looks_sensitive("Debugging password reset flow.",("password",))
    assert memory_engine._looks_sensitive("My refresh token is abcdef123.",())


def test_valid_citation_with_unsupported_claim_abstains(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Rajeev is my manager.","Rajeev")
    memory=db.scalars(select(Memory)).one()
    monkeypatch.setattr(hey_kivi,"plan_query",lambda *a,**k:(QueryPlan(predicates=["manager"]),set(),{}))
    monkeypatch.setattr(hey_kivi,"retrieve_memories",lambda *a,**k:([(memory,1)],1))
    monkeypatch.setattr(hey_kivi,"retrieve_history",lambda *a,**k:[])
    monkeypatch.setattr(hey_kivi.provider,"enabled",True)
    def fake_chat(*args,**kwargs):
        if args[-1]=="evidence_verdict":return {"supported":False,"reason":"Source says manager, not spouse."},{}
        return {"answer":"Rajeev is your spouse.","supported":True,"applied_preferences":[],
                "claims":[{"text":"Rajeev is your spouse.","evidence":["E1"]}]},{}
    monkeypatch.setattr(hey_kivi.provider,"chat_json",fake_chat)
    assert "know" in hey_kivi.answer_query(db,"Who is my manager?","test")["response"]


def test_generic_csv_import_and_controls(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import get_db
    db=db_session();app.dependency_overrides[get_db]=lambda: db
    monkeypatch.setattr(memory_engine,"extract_candidates",lambda db,row:([{**candidate("Leela",predicate="curator"),"evidence_text":row.formatted_text}],{},[]))
    try:
        client=TestClient(app)
        data=client.post("/api/import",files={"file":("history.csv","raw_asr,formatted_output,timestamp,app\nleela is curator,Leela is my curator.,2026-09-01T10:00:00+05:30,Slack","text/csv")}).json()
        assert data["processed"]==1 and not data["failed"]
        replay=client.post("/api/import",files={"file":("history.csv","raw_asr,formatted_output,timestamp,app\nleela is curator,Leela is my curator.,2026-09-01T10:00:00+05:30,Slack","text/csv")}).json()
        assert replay["results"][0]["replayed"] is True
        memory=db.scalars(select(Memory)).one();assert len(memory.sources)==1
        assert memory.sources[0].interaction.occurred_at==datetime(2026,9,1,4,30)
        assert client.patch(f"/api/memories/{memory.id}",json={"value":"Maya"}).status_code==200
        active=db.scalars(select(Memory).where(Memory.status=="active")).one();assert active.value=="Maya"
        assert client.delete(f"/api/memories/{active.id}").status_code==200
        assert db.scalars(select(ForgetBoundary)).one()
        assert client.get("/api/decisions").json()[0]["action"]=="delete"
        bad=client.post("/api/import",files={"file":("bad.json",'[{}]','application/json')}).json();assert bad["failed"]==1
    finally:app.dependency_overrides.clear()


def test_new_contradiction_withdraws_inferred_preference(monkeypatch):
    db=db_session()
    for day in range(3): learn(db,monkeypatch,"Make email concise.","concise",day,memory_type="preference",predicate="length",explicitness="inferred",scope={"app":"email"})
    assert db.scalars(select(Memory)).one().status=="active"
    learn(db,monkeypatch,"Make email detailed.","detailed",3,memory_type="preference",predicate="length",explicitness="inferred",scope={"app":"email"})
    assert all(m.status=="pending" for m in db.scalars(select(Memory)))


def test_unsupported_identity_qualifiers_do_not_split_user(monkeypatch):
    db=db_session()
    learn(db,monkeypatch,"Rajeev is my manager.","Rajeev",subject_qualifier="user",value_qualifier="person")
    learn(db,monkeypatch,"Ananya is now my manager.","Ananya",1,subject_qualifier="first person",value_qualifier="person")
    assert len(list(db.scalars(select(Entity).where(Entity.normalized_name=="user"))))==1
    assert db.scalars(select(Memory).where(Memory.status=="active")).one().value=="Ananya"


def test_historical_state_uses_validity_not_source_date(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Rajeev is my manager.","Rajeev")
    learn(db,monkeypatch,"Priya is now my manager.","Priya",5)
    plan=QueryPlan(intent="historical",time_axis="validity",time_from=datetime(2026,9,3),time_until=datetime(2026,9,4))
    rows,_=retrieve_memories(db,"Who was my manager?",plan=plan)
    assert [m.value for m,_ in rows]==["Rajeev"]


def test_active_source_can_supply_unpromoted_clause(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Aaditya reviews Atlas. We call Aaditya Aadi.","Aadi",subject="Aaditya",predicate="nickname")
    rows=retrieve_history(db,"What did Aaditya review?",plan=QueryPlan(intent="historical"))
    assert rows and "reviews Atlas" in rows[0][0].formatted_text


def test_original_unrelated_evidence_remains_safe_after_forget(monkeypatch):
    from app.services.lifecycle import safe_evidence
    db=db_session();learn(db,monkeypatch,"Rajeev is my manager.","Rajeev")
    learn(db,monkeypatch,"Atlas uses FastAPI.","FastAPI",subject="Atlas",predicate="backend",memory_type="fact")
    learn(db,monkeypatch,"Forget my manager.","any",1,proposed_action="delete")
    memory=db.scalars(select(Memory).where(Memory.predicate=="backend")).one()
    assert safe_evidence(db,memory,memory.sources[0])=="Atlas uses FastAPI."


def test_empty_scope_and_alias_literal_are_canonical(monkeypatch):
    from app.services.lifecycle import scope_json
    assert scope_json({"app":None,"context":None})=="global"
    db=db_session();learn(db,monkeypatch,"We call Aaditya Aadi.","Aadi",subject="Aaditya",predicate="nickname",entities=[{"name":"Aaditya","kind":"person","qualifier":"","aliases":["Aadi"],"evidence_text":"We call Aaditya Aadi."}])
    memory=db.scalars(select(Memory)).one();assert memory.value=="Aadi" and memory.value_entity_id is None
    assert lookup(db,"Aadi")[0].name=="Aaditya"


def test_global_explicit_preference_blocks_narrow_inference(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Always keep updates concise.","concise",memory_type="preference",predicate="length")
    for day in range(1,4):learn(db,monkeypatch,"Make email detailed.","detailed",day,memory_type="preference",predicate="length",explicitness="inferred",scope={"app":"email"})
    assert db.scalars(select(Memory)).one().value=="concise"


def test_unknown_scope_cannot_promote_global_behavior(monkeypatch):
    db=db_session()
    for day in range(4):learn(db,monkeypatch,"Shorter please.","concise",day,memory_type="preference",predicate="length",explicitness="inferred")
    assert not list(db.scalars(select(Memory)))


def test_extraction_cannot_default_missing_subject_to_user():
    from app.services.memory_contract import MemoryCandidate
    from pydantic import ValidationError
    c=candidate("Atlas",predicate="reviews");del c["subject"]
    try:MemoryCandidate.model_validate(c)
    except ValidationError:pass
    else:raise AssertionError("Missing actor must never default to the user")


def test_citation_to_withheld_prior_evidence_abstains(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Priya might become my manager.","Priya",certainty="tentative",temporal_status="future")
    learn(db,monkeypatch,"Priya is officially my manager.","Priya",1)
    memory=db.scalars(select(Memory)).one();old_source=memory.sources[0].interaction_id
    monkeypatch.setattr(hey_kivi,"plan_query",lambda *a,**k:(QueryPlan(predicates=["manager"]),set(),{}))
    monkeypatch.setattr(hey_kivi,"retrieve_memories",lambda *a,**k:([(memory,1)],1))
    monkeypatch.setattr(hey_kivi,"retrieve_history",lambda *a,**k:[])
    monkeypatch.setattr(hey_kivi.provider,"enabled",True)
    def fake_chat(*args,**kwargs):
        assert args[-1]!="evidence_verdict", "Withheld evidence citation must fail before model verification"
        return {"answer":"Priya is your manager.","supported":True,"used_memory_ids":[memory.id],"used_interaction_ids":[old_source],
                "claims":[{"text":"Priya is your manager.","memory_ids":[memory.id],"interaction_ids":[old_source]}]},{}
    monkeypatch.setattr(hey_kivi.provider,"chat_json",fake_chat)
    assert "know" in hey_kivi.answer_query(db,"Who is my manager?","test")["response"]


def test_ambiguous_or_unknown_qualified_forget_does_not_delete(monkeypatch):
    db=db_session()
    for day,qualifier in enumerate(["museum","cycling"]):
        learn(db,monkeypatch,f"Alex from {qualifier} reviews Atlas.","Atlas",day,
              subject="Alex",subject_qualifier=qualifier,predicate="review_responsibility")
    for day,qualifier in enumerate(["","school"],3):
        text="Forget Alex's reviews." if not qualifier else "Forget Alex from school's reviews."
        row=learn(db,monkeypatch,text,"any",day,subject="Alex",subject_qualifier=qualifier,
                  predicate="review_responsibility",proposed_action="delete")
        decision=db.scalars(select(MemoryDecision).where(MemoryDecision.interaction_id==row.id)).one()
        assert decision.action=="clarify"
    assert [m.status for m in db.scalars(select(Memory))]==["active","active"]
    assert not list(db.scalars(select(ForgetBoundary)))


def test_unrelated_entity_metadata_cannot_block_supported_fact(monkeypatch):
    db=db_session()
    learn(db,monkeypatch,"Dina is coordinator of Aspen Kitchen.","Aspen Kitchen",subject="Dina",predicate="coordinates")
    row=learn(db,monkeypatch,"Aspen Kitchen uses steam ovens.","steam ovens",1,
              memory_type="fact",subject="Aspen Kitchen",predicate="uses_technique",
              entities=[{"name":"Dina","kind":"person","qualifier":"coordinator","aliases":["DinaBee"],
                         "evidence_text":"Dina is coordinator of Aspen Kitchen."}])
    assert any(s.interaction_id==row.id for m in db.scalars(select(Memory)) for s in m.sources)
    assert not lookup(db,"DinaBee")
    decision=db.scalars(select(MemoryDecision).where(MemoryDecision.interaction_id==row.id)).one()
    assert json.loads(decision.candidate_json).get("discarded_entity_mentions")


def test_extraction_context_recovers_old_relevant_project(monkeypatch):
    db=db_session()
    learn(db,monkeypatch,"Orion uses SQLite.","SQLite",subject="Orion",predicate="uses",memory_type="fact")
    for day in range(1,45):
        learn(db,monkeypatch,f"Project{day} uses Tool{day}.",f"Tool{day}",day,
              subject=f"Project{day}",predicate="uses",memory_type="fact")
    relevant=memory_engine.extraction_context(db,"Correction: Orion now uses DuckDB.")
    assert [m.subject for m in relevant]==["Orion"]
    assert len(memory_engine.extraction_context(db,"Actually, use that option instead."))==8


def test_cooccurrence_does_not_license_entity_alias(monkeypatch):
    db=db_session();text="Ari reviews Atlas."
    row=learn(db,monkeypatch,text,"Atlas",subject="Ari",predicate="reviews",
              entities=[{"name":"Ari","kind":"person","qualifier":"","aliases":["Atlas"],"evidence_text":text}])
    assert not lookup(db,"Atlas") or all(e.name!="Ari" for e in lookup(db,"Atlas"))
    assert any(s.interaction_id==row.id for m in db.scalars(select(Memory)) for s in m.sources)


def test_forget_alias_binding_cannot_resolve_old_person(monkeypatch):
    db=db_session();text="Aaditya, also called Aadi, reviews Atlas."
    learn(db,monkeypatch,text,"Aadi",subject="Aaditya",predicate="alias",memory_type="fact",cardinality="multi",
          entities=[{"name":"Aaditya","kind":"person","qualifier":"","aliases":["Aadi"],"evidence_text":text}])
    learn(db,monkeypatch,"Aaditya coordinates Orion.","Orion",1,subject="Aaditya",predicate="coordinates")
    learn(db,monkeypatch,"Forget the alias Aadi for Aaditya.","Aadi",2,subject="Aaditya",predicate="alias",
          memory_type="fact",cardinality="multi",proposed_action="delete")
    assert not lookup(db,"Aadi")
    alias_rows=[m for m in db.scalars(select(Memory)) if m.predicate=="alias"]
    assert alias_rows[0].status=="deleted"
    assert any(m.status=="active" and m.predicate=="coordinates" for m in db.scalars(select(Memory)))
    actor=lookup(db,"Aaditya")[0]
    ranked,_=retrieve_memories(db,"Aaditya coordinates Orion",plan=QueryPlan(predicates=["coordinates"]),entity_ids={actor.id})
    assert [m.value for m,_ in ranked]==["Orion"]
    assert safe_evidence(db,ranked[0][0],ranked[0][0].sources[0])=="Aaditya coordinates Orion."



def test_verbatim_unrelated_text_cannot_authorize_delete(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Rajeev is my manager.","Rajeev")
    row=learn(db,monkeypatch,"Thanks.","any",1,proposed_action="delete")
    assert db.scalars(select(Memory)).one().status=="active"
    assert not list(db.scalars(select(ForgetBoundary)))
    assert db.scalars(select(MemoryDecision).where(MemoryDecision.interaction_id==row.id)).one().action=="clarify"


def test_unpromoted_alias_certificate_can_be_forgotten(monkeypatch):
    db=db_session();text="Aaditya, also called Aadi, reviews Atlas."
    learn(db,monkeypatch,text,"Atlas",subject="Aaditya",predicate="reviews",
          entities=[{"name":"Aaditya","kind":"person","qualifier":"","aliases":["Aadi"],"evidence_text":text}])
    assert lookup(db,"Aadi")
    learn(db,monkeypatch,"Forget all aliases of Aaditya.","any",1,subject="Aaditya",predicate="alternate_name",proposed_action="delete")
    assert not lookup(db,"Aadi")
    assert db.scalars(select(Memory)).one().status=="active"


def test_forgotten_alias_cannot_identify_canonical_actor(monkeypatch):
    db=db_session();text="We call Aaditya Aadi."
    learn(db,monkeypatch,text,"Aadi",subject="Aaditya",predicate="nickname",memory_type="fact",cardinality="multi",
          entities=[{"name":"Aaditya","kind":"person","qualifier":"","aliases":["Aadi"],"evidence_text":text}])
    learn(db,monkeypatch,"Forget Aaditya's nickname Aadi.","Aadi",1,subject="Aaditya",predicate="nickname",cardinality="multi",proposed_action="delete")
    row=learn(db,monkeypatch,"Aadi reviews Orion.","Orion",2,subject="Aaditya",predicate="reviews")
    assert db.scalars(select(MemoryDecision).where(MemoryDecision.interaction_id==row.id)).one().action=="clarify"
    assert not lookup(db,"Aadi")


def test_explicit_alias_relearn_uses_new_certificate(monkeypatch):
    db=db_session();text="We call Aaditya Aadi."
    entities=[{"name":"Aaditya","kind":"person","qualifier":"","aliases":["Aadi"],"evidence_text":text}]
    learn(db,monkeypatch,text,"Aadi",subject="Aaditya",predicate="nickname",memory_type="fact",cardinality="multi",entities=entities)
    learn(db,monkeypatch,"Forget Aaditya's nickname Aadi.","Aadi",1,subject="Aaditya",predicate="nickname",cardinality="multi",proposed_action="delete")
    assert not lookup(db,"Aadi")
    text="Remember, Aaditya is also called Aadi."
    learn(db,monkeypatch,text,"Aadi",2,subject="Aaditya",predicate="nickname",memory_type="fact",cardinality="multi",
          entities=[{"name":"Aaditya","kind":"person","qualifier":"","aliases":["Aadi"],"evidence_text":text}])
    assert lookup(db,"Aadi")[0].name=="Aaditya"
    assert [m.status for m in db.scalars(select(Memory))]==["deleted","active"]


def test_nonretention_phrase_can_forget_existing_slot(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Rajeev is my manager.","Rajeev")
    learn(db,monkeypatch,"Don't remember who my manager is anymore.","any",1,proposed_action="delete")
    assert db.scalars(select(Memory)).one().status=="deleted"
    assert retrieve_memories(db,"Who is my manager?",plan=QueryPlan(predicates=["manager"]))[0]==[]
    assert retrieve_history(db,"Who did I report to?",plan=QueryPlan(intent="historical"))==[]


def test_nonretention_exclusion_survives_extractor_failure(monkeypatch):
    db=db_session();row=interaction(db,"Don't remember this: locker code is 804.",datetime(2026,9,1))
    def fail(*args):raise RuntimeError("provider unavailable")
    monkeypatch.setattr(memory_engine,"extract_candidates",fail)
    import pytest
    with pytest.raises(RuntimeError):memory_engine.process_interaction(db,row)
    db.refresh(row)
    assert row.retrieval_blocked and row.processing_status=="failed"
    assert retrieve_history(db,"locker code",plan=QueryPlan(intent="historical"))==[]


def test_reciprocal_alias_mentions_share_canonical_identity(monkeypatch):
    db=db_session();db.autoflush=False;learn(db,monkeypatch,"Vera coordinates Quartz.","Quartz",subject="Vera",predicate="coordinates")
    text="Vera is also called VeraBee. VeraBee reviews Quartz."
    learn(db,monkeypatch,text,"Quartz",1,subject="VeraBee",predicate="reviews",
          entities=[{"name":"Vera","kind":"person","qualifier":"","aliases":["VeraBee"],"evidence_text":"Vera is also called VeraBee."},
                    {"name":"VeraBee","kind":"person","qualifier":"","aliases":["Vera"],"evidence_text":"Vera is also called VeraBee."}])
    assert len(lookup(db,"Vera"))==len(lookup(db,"VeraBee"))==1
    assert lookup(db,"Vera")[0].id==lookup(db,"VeraBee")[0].id
    assert any(m.status=="active" and m.subject=="Vera" and m.predicate=="reviews" for m in db.scalars(select(Memory)))


def test_grounded_alias_claim_includes_binding_source(monkeypatch):
    db=db_session();text="We call Aaditya Aadi. Aadi reviews Atlas."
    learn(db,monkeypatch,text,"Atlas",subject="Aadi",predicate="reviews",
          entities=[{"name":"Aaditya","kind":"person","qualifier":"","aliases":["Aadi"],"evidence_text":"We call Aaditya Aadi."}])
    memory=db.scalars(select(Memory)).one()
    memory.sources[0].evidence_text="Aadi reviews Atlas.";db.commit()
    monkeypatch.setattr(hey_kivi,"plan_query",lambda *a,**k:(QueryPlan(predicates=["reviews"]),set(),{}))
    monkeypatch.setattr(hey_kivi,"retrieve_memories",lambda *a,**k:([(memory,1)],1))
    monkeypatch.setattr(hey_kivi,"retrieve_history",lambda *a,**k:[])
    monkeypatch.setattr(hey_kivi.provider,"enabled",True)
    def fake_chat(system,user,schema,name):
        data=json.loads(user)
        context=data.get("evidence",data.get("memories",[]))
        excerpts=[e["excerpt"] for m in context for e in m.get("sources",m.get("source_evidence",[]))]
        supported="We call Aaditya Aadi." in excerpts and "Aadi reviews Atlas." in excerpts
        if name=="evidence_verdict":return {"supported":supported,"reason":"Actor identity needs the binding and the review statement."},{}
        return {"answer":"Aaditya reviews Atlas.","supported":supported,"applied_preferences":[],
                "claims":[{"text":"Aaditya reviews Atlas.","evidence":["E1"]}]},{}
    monkeypatch.setattr(hey_kivi.provider,"chat_json",fake_chat)
    result=hey_kivi.answer_query(db,"Who reviews Atlas?","test")
    assert result["response"]=="Aaditya reviews Atlas."
    assert {e["excerpt"] for e in result["memories"][0]["source_evidence"]}=={"We call Aaditya Aadi.","Aadi reviews Atlas."}


def test_forget_uses_same_supported_scope_normalization_as_admission(monkeypatch):
    db=db_session();learn(db,monkeypatch,"Sima is my manager.","Sima")
    learn(db,monkeypatch,"Forget who my manager is.","any",1,proposed_action="delete",
          scope={"app":"Notes","context":"unknown","project":None,"recipient":None})
    assert db.scalars(select(Memory)).one().status=="deleted"
    assert db.scalars(select(ForgetBoundary)).one().scope=="global"


def forgotten_alias_role(db,monkeypatch):
    learn(db,monkeypatch,"Dorian is also called Dori. Dori coordinates Paper Atlas.","Paper Atlas",subject="Dori",predicate="coordinates",cardinality="multi",canonical_text="Dori coordinates Paper Atlas.",
          entities=[{"name":"Dorian","kind":"person","qualifier":"","aliases":["Dori"],"evidence_text":"Dorian is also called Dori."}])
    learn(db,monkeypatch,"Dorian coordinates Paper Atlas.","Paper Atlas",1,subject="Dorian",predicate="coordinates",cardinality="multi",canonical_text="Dorian coordinates Paper Atlas.")
    learn(db,monkeypatch,"Forget all aliases of Dorian.","any",2,subject="Dorian",predicate="alias",proposed_action="delete")
    return db.scalars(select(Memory).where(Memory.predicate=="coordinates")).one()


def test_forgotten_alias_query_cannot_use_similar_primary_name(monkeypatch):
    db=db_session();forgotten_alias_role(db,monkeypatch)
    def forbidden_plan(*a,**k):raise AssertionError("Forgotten alias must not reach model name inference")
    monkeypatch.setattr(hey_kivi,"plan_query",forbidden_plan)
    result=hey_kivi.answer_query(db,"What does Dori coordinate?","test")
    assert "don't know" in result["response"].replace("\u2019","'")
    assert result["memories"]==[] and result["history_evidence"]==[]
    assert result["model_usage"]["retrieval_errors"]==[]


def test_forgotten_alias_output_rejected_even_if_verifier_approves(monkeypatch):
    db=db_session();memory=forgotten_alias_role(db,monkeypatch)
    monkeypatch.setattr(hey_kivi,"plan_query",lambda *a,**k:(QueryPlan(predicates=["coordinates"]),set(),{}))
    monkeypatch.setattr(hey_kivi,"retrieve_memories",lambda *a,**k:([(memory,1)],1))
    monkeypatch.setattr(hey_kivi,"retrieve_history",lambda *a,**k:[])
    monkeypatch.setattr(hey_kivi.provider,"enabled",True)
    def fake_chat(system,user,schema,name):
        if name=="evidence_verdict":return {"supported":True,"reason":"Deliberately overconfident verifier."},{}
        return {"answer":"Dori coordinates Paper Atlas.","supported":True,"applied_preferences":[],
                "claims":[{"text":"Dori coordinates Paper Atlas.","evidence":["E1"]}]},{}
    monkeypatch.setattr(hey_kivi.provider,"chat_json",fake_chat)
    result=hey_kivi.answer_query(db,"What does Dorian coordinate?","test")
    assert "Paper Atlas" not in result["response"]
    assert result["memories"]==[]


def test_core_subject_identity_survives_empty_auxiliary_qualifier(monkeypatch):
    db=db_session()
    learn(db,monkeypatch,"Alex from the museum reviews Cedar.","Cedar",subject="Alex",subject_qualifier="museum",predicate="reviews",
          entities=[{"name":"Alex","kind":"person","qualifier":"","aliases":[],"evidence_text":"Alex from the museum"}])
    memory=db.scalars(select(Memory)).one()
    assert db.get(Entity,memory.subject_entity_id).qualifier=="museum"


def test_core_object_identity_survives_empty_auxiliary_qualifier(monkeypatch):
    db=db_session()
    learn(db,monkeypatch,"Cedar collaborates with Alex from the museum.","Alex",subject="Cedar",value_qualifier="museum",predicate="collaborates_with",
          entities=[{"name":"Alex","kind":"person","qualifier":"","aliases":[],"evidence_text":"Alex from the museum"}])
    memory=db.scalars(select(Memory)).one()
    assert db.get(Entity,memory.value_entity_id).qualifier=="museum"


def test_core_alias_fact_recovers_missing_optional_alias_metadata(monkeypatch):
    db=db_session();text="Dorian is also called Dori. Dori coordinates Paper Atlas."
    row=interaction(db,text,datetime(2026,9,1))
    alias=candidate("Dori");alias.update(subject="Dorian",predicate="alias",memory_type="relationship",canonical_text="Dorian is also called Dori.",evidence_text="Dorian is also called Dori.",entities=[{"name":"Dorian","kind":"person","qualifier":"","aliases":[],"evidence_text":"Dorian is also called Dori."},{"name":"Dori","kind":"person","qualifier":"","aliases":[],"evidence_text":"Dorian is also called Dori."}])
    alias["entities"].reverse()  # Alias participant may precede its primary in model output.
    role=candidate("Paper Atlas");role.update(subject="Dori",predicate="coordinates",cardinality="multi",canonical_text="Dori coordinates Paper Atlas.",evidence_text="Dori coordinates Paper Atlas.")
    monkeypatch.setattr(memory_engine,"extract_candidates",lambda *a:([role,alias],{},[]))
    memory_engine.process_interaction(db,row)
    assert len(lookup(db,"Dori"))==1 and lookup(db,"Dori")[0].id==lookup(db,"Dorian")[0].id
    memories=list(db.scalars(select(Memory)))
    assert next(m for m in memories if m.predicate=="alias").value_entity_id is None
    assert next(m for m in memories if m.predicate=="coordinates").subject_entity_id==lookup(db,"Dorian")[0].id


def test_unrecognized_planner_predicate_preserves_semantic_current_candidates(monkeypatch):
    db=db_session()
    learn(db,monkeypatch,"Mira is the coordinator of Cedar Archive.","Mira",subject="Cedar Archive",predicate="coordinator")
    learn(db,monkeypatch,"Omar might coordinate Cedar Archive next month.","Omar",1,subject="Cedar Archive",predicate="coordinator",certainty="tentative",temporal_status="future")
    learn(db,monkeypatch,"Cleo is coordinator of Willow Clinic.","Willow Clinic",2,subject="Cleo",predicate="coordinator_of")
    project=lookup(db,"Cedar Archive")[0]
    ranked,_=retrieve_memories(db,"Who currently coordinates Cedar Archive?",plan=QueryPlan(intent="current",predicates=["coordinator_of"]),entity_ids={project.id})
    assert [m.value for m,_ in ranked]==["Mira"]


def test_ambiguous_former_holder_does_not_block_distinct_core_correction(monkeypatch):
    db=db_session()
    from app.services.entities import resolve
    resolve(db,"Mira","museum");resolve(db,"Mira","cycling club")
    text="Tessa is coordinator of Cedar Archive, replacing Mira."
    learn(db,monkeypatch,text,"Tessa",subject="Cedar Archive",predicate="coordinator",
          entities=[{"name":"Mira","kind":"other","qualifier":"","aliases":[],"evidence_text":"replacing Mira"}])
    stored=list(db.scalars(select(Memory)))
    assert len(stored)==1 and stored[0].value=="Tessa" and stored[0].status=="active"
    assert len(lookup(db,"Mira"))==2
    decision=list(db.scalars(select(MemoryDecision)))[-1]
    assert "Ambiguous auxiliary participant" in decision.candidate_json
