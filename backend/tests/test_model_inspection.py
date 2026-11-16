"""Model compatibility probes use hand-written numeric fixtures, not trained evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from test_intent import _model, CATEGORIES

ROOT=Path(__file__).resolve().parents[2]


def test_inspector_reports_digest_compatibility_and_missing_provenance_without_execution(tmp_path):
    model=tmp_path/'model.json';model.write_text(json.dumps(_model()))
    categories=tmp_path/'categories.json';categories.write_text(json.dumps(CATEGORIES))
    run=subprocess.run([sys.executable,'-S','-m','ml.inspect_model','--model',str(model),'--categories',str(categories)],cwd=ROOT,capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    report=json.loads(run.stdout)
    assert report['model_version']==hashlib.sha256(model.read_bytes()).hexdigest()
    assert report['compatible'] is True and report['provenance']=='missing'
    assert 'coef' not in report and 'vocabulary' not in report
    categories.write_text(json.dumps(CATEGORIES[:1]))
    run=subprocess.run([sys.executable,'-S','-m','ml.inspect_model','--model',str(model),'--categories',str(categories)],cwd=ROOT,capture_output=True,text=True)
    assert run.returncode==2
    assert json.loads(run.stdout)['compatible'] is False


def test_inspection_distinguishes_explicit_mapping_from_same_name_compatibility(tmp_path):
    from ml.inspect_model import inspect_model
    model=_model();model['labels']=['refund_request','credential_reset']
    path=tmp_path/'model.json';path.write_text(json.dumps(model))
    mapping=tmp_path/'map.json';mapping.write_text(json.dumps({'approved':True,'approved_by':'DEMO fixture only','model_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'labels':{'refund_request':1,'credential_reset':2}}))
    report=inspect_model(path,CATEGORIES,mapping_path=mapping)
    assert report['compatible'] and report['compatibility_mode']=='explicit_mapping'
    assert report['mapping_version']==hashlib.sha256(mapping.read_bytes()).hexdigest()
    assert report['compatibility_error'] is None
    invalid=inspect_model(path,[{'name':'missing ID'}],mapping_path=mapping)
    assert not invalid['compatible'] and invalid['compatibility_error']
