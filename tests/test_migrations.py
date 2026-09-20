import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]

def initialize(path):
    env=dict(os.environ,KIVI_DB_PATH=str(path),KIVI_PROVIDER='offline')
    result=subprocess.run([sys.executable,'-c','from app.db import init_db; init_db()'],cwd=ROOT,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()==('0003_identity_boundaries',)
        assert {'subject_entity_id','value_entity_id'} <= {r[1] for r in db.execute('PRAGMA table_info(forget_boundaries)')}
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert len([r for r in db.execute('PRAGMA foreign_key_list(forget_boundaries)') if r[2]=='entities'])==2

def test_fresh_migration_and_repeat_startup(tmp_path):
    path=tmp_path/'fresh.db'
    initialize(path)
    initialize(path)

@pytest.mark.parametrize('versioned',[True,False])
def test_existing_v2_boundary_survives_identity_upgrade(tmp_path,versioned):
    path=tmp_path/'old-v2.db'
    initialize(path)
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE forget_boundaries')
        db.execute('CREATE TABLE forget_boundaries(id INTEGER PRIMARY KEY, subject VARCHAR(200) NOT NULL, predicate VARCHAR(200) NOT NULL, scope TEXT NOT NULL, value TEXT, occurred_at DATETIME NOT NULL, interaction_id INTEGER REFERENCES interactions(id))')
        db.execute("INSERT INTO forget_boundaries VALUES(1,'user','manager','global','Rajeev','2026-07-15',NULL)")
        if versioned: db.execute("UPDATE alembic_version SET version_num='0002_v2_foundation'")
        else: db.execute('DROP TABLE alembic_version')
    initialize(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT subject,predicate,value,subject_entity_id,value_entity_id FROM forget_boundaries').fetchone()==('user','manager','Rajeev',None,None)
