from sqlalchemy import select
from tests.test_memory_lifecycle import db_session
from tests.test_v2_behavior import learn
from app.services.entities import lookup
from app.services.retrieval import retrieve_memories
from app.services.query_context import QueryPlan


def seed(db,monkeypatch):
    for project,tool in [("Orchid Lab","microscope"),("Copper Farm","soil probe")]:
        learn(db,monkeypatch,f"I work on {project}.","user",subject=project,predicate="work_on",cardinality="multi")
        learn(db,monkeypatch,f"{project} uses {tool}.",tool,subject=project,predicate="uses",memory_type="fact")
        learn(db,monkeypatch,f"{project} is due October 20.","October 20",subject=project,predicate="deadline",memory_type="fact")


def test_shared_user_does_not_expand_into_other_project(monkeypatch):
    db=db_session();seed(db,monkeypatch)
    plan=QueryPlan(intent="draft",project="Orchid Lab",predicates=["work_on","deadline"])
    ranked,_=retrieve_memories(db,"Compose an Orchid Lab progress note with equipment and due date",plan=plan,entity_ids={lookup(db,"Orchid Lab")[0].id})
    assert not any(m.subject=="Copper Farm" for m,_ in ranked)
    assert any(m.value=="microscope" for m,_ in ranked)


def test_history_keeps_previous_slot_despite_shared_actor(monkeypatch):
    db=db_session();seed(db,monkeypatch)
    learn(db,monkeypatch,"Ada coordinates Orchid Lab.","Ada",subject="Orchid Lab",predicate="coordinator")
    learn(db,monkeypatch,"Bea replaced Ada as Orchid Lab coordinator.","Bea",1,subject="Orchid Lab",predicate="coordinator",change_kind="replace")
    for i in range(12):
        learn(db,monkeypatch,f"I coordinated Site {i} in the past.",f"Site {i}",subject="user",predicate="coordinated",temporal_status="historical",cardinality="multi")
    ranked,_=retrieve_memories(db,"Who coordinated Orchid Lab before Bea?",plan=QueryPlan(intent="historical",project="Orchid Lab",predicates=["coordinated"]),entity_ids={lookup(db,"Orchid Lab")[0].id})
    assert any(m.value=="Ada" and m.status=="superseded" for m,_ in ranked)
    assert not any(m.value.startswith("Site ") for m,_ in ranked)


def test_draft_does_not_promote_tentative_tool(monkeypatch):
    db=db_session();seed(db,monkeypatch)
    learn(db,monkeypatch,"Orchid Lab might use lasers.","lasers",1,subject="Orchid Lab",predicate="uses",memory_type="fact",certainty="tentative")
    ranked,_=retrieve_memories(db,"Draft current equipment summary for Orchid Lab",plan=QueryPlan(intent="draft",project="Orchid Lab"),entity_ids={lookup(db,"Orchid Lab")[0].id})
    assert all(m.certainty=="confirmed" for m,_ in ranked)


def test_foreign_tool_rejected_but_explicit_comparison_allowed(monkeypatch):
    from app.services.hey_kivi import contamination_terms
    db=db_session();seed(db,monkeypatch)
    from app.models import Entity
    for name in ("Orchid Lab","Copper Farm"):lookup(db,name)[0].kind="project"
    db.flush()
    plan=QueryPlan(intent="draft",project="Orchid Lab")
    assert "soil probe" in contamination_terms(db,"Summarize Orchid Lab",plan,"We use a soil probe.",[],[])
    assert not contamination_terms(db,"Compare Orchid Lab and Copper Farm soil probe",plan,"Copper Farm uses a soil probe.",[],[])


def test_generic_user_is_not_a_foreign_project_fact(monkeypatch):
    from app.services.hey_kivi import contamination_terms
    db=db_session();seed(db,monkeypatch)
    for name in ("Orchid Lab","Copper Farm"):lookup(db,name)[0].kind="project"
    learn(db,monkeypatch,"Copper Farm is worked on by user.","user",subject="Copper Farm",predicate="work_on",memory_type="fact")
    assert not contamination_terms(db,"Summarize Orchid Lab",QueryPlan(project="Orchid Lab"),"User works here.",[],[])


def test_tool_comparison_includes_format_without_merging_roles(monkeypatch):
    db=db_session()
    learn(db,monkeypatch,"Orchid Lab stores images in PNG.","PNG",subject="Orchid Lab",predicate="format",memory_type="fact")
    learn(db,monkeypatch,"Copper Farm uses sensors.","sensors",subject="Copper Farm",predicate="uses",memory_type="fact")
    for name in ("Orchid Lab","Copper Farm"):lookup(db,name)[0].kind="project"
    ranked,_=retrieve_memories(db,"Compare tools on Orchid Lab and Copper Farm",plan=QueryPlan(predicates=["uses"]),entity_ids={lookup(db,n)[0].id for n in ("Orchid Lab","Copper Farm")})
    assert {m.value for m,_ in ranked}=={"PNG","sensors"}
