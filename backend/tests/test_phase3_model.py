"""Non-research engineering fixtures: configuration, integrity, mapping and isolation."""
import hashlib
import json
from pathlib import Path
import pytest
from ml.dataset import read_dataset
from ml.intent import load_model, model_scores, predict
from ml.train import train
from ml.evaluate import evaluate
from test_intent import _source, _dataset, _model, CATEGORIES


def test_numeric_model_tampering_is_rejected_by_expected_digest(tmp_path):
    path=tmp_path/'numeric.json';path.write_text(json.dumps(_model()))
    expected=hashlib.sha256(path.read_bytes()).hexdigest()
    assert load_model(path,expected_sha256=expected)['integrity']=='pinned'
    changed=_model();changed['coef']=[[3.0]]
    path.write_text(json.dumps(changed))
    result=predict('退款',CATEGORIES,path,expected_sha256=expected)
    assert result['source']=='rules' and result['model_version'] is None
    with pytest.raises(ValueError,match='摘要|完整性'):
        load_model(path,expected_sha256=expected)


def test_training_configuration_is_recorded_and_numeric_export_matches(tmp_path):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from ml.intent import normalize_text
    data=_dataset(tmp_path/'train.jsonl',[('退款申请','退款'),('退钱处理','退款'),('登录密码','账户'),('重置密码','账户')])
    output=tmp_path/'model.json'
    config={'ngram_range':[1,2],'max_features':30,'C':0.4,'max_iter':300,'random_state':7}
    metadata=train(data,_source(tmp_path),output,config=config)
    model=load_model(output)
    assert metadata['parameters']['C']==0.4 and model['ngram_range']==[1,2]
    assert model['integrity']=='manifest'
    sidecar=output.with_suffix('.json.manifest.json')
    assert json.loads(sidecar.read_text())['model_sha256']==hashlib.sha256(output.read_bytes()).hexdigest()
    texts,labels,_=read_dataset(data)
    vectorizer=TfidfVectorizer(analyzer='char',ngram_range=(1,2),max_features=30,preprocessor=normalize_text,lowercase=False)
    clf=LogisticRegression(C=0.4,max_iter=300,random_state=7).fit(vectorizer.fit_transform(texts),labels)
    assert model_scores('退款处理',model)==pytest.approx(clf.predict_proba(vectorizer.transform(['退款处理']))[0].tolist(),abs=1e-12)
    payload=json.loads(output.read_text());payload['intercept'][0]+=1
    output.write_text(json.dumps(payload))
    with pytest.raises(ValueError,match='摘要|完整性'):load_model(output)


def test_declared_partition_requires_an_explicit_matching_training_role(tmp_path):
    data=tmp_path/'declared.jsonl'
    data.write_text('\n'.join(json.dumps({'text':text,'label':label,'source_partition':'test'}) for text,label in [('DEMO退费','a'),('DEMO密码','b')]))
    with pytest.raises(ValueError,match='分区'):
        train(data,_source(tmp_path),tmp_path/'wrong.json',config={'data_partition':'train'})
    assert not (tmp_path/'wrong.json').exists()
    with pytest.raises(ValueError,match='分区'):
        train(data,_source(tmp_path),tmp_path/'unspecified.json')


def test_explicit_mapping_does_not_replace_source_model_labels_or_guess_unknowns(tmp_path):
    model=_model();model['labels']=['refund_request','credential_reset']
    path=tmp_path/'model.json';path.write_text(json.dumps(model))
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    mapping=tmp_path/'map.json'
    content={'model_sha256':digest,'approved_by':'DEMO engineering fixture only','approved':True,'labels':{'refund_request':1,'credential_reset':None}}
    mapping.write_text(json.dumps(content))
    result=predict('退',CATEGORIES,path,mapping_path=mapping)
    assert result['source']=='model' and result['predicted_label']=='refund_request' and result['category_id']==1
    assert result['mapping_version']==hashlib.sha256(mapping.read_bytes()).hexdigest()
    manual=predict('退',[{**CATEGORIES[0],'active':False},CATEGORIES[1]],path,mapping_path=mapping)
    assert manual['source']=='fallback' or manual['source']=='rules'
    assert manual['needs_manual']
    content['approved']=False;mapping.write_text(json.dumps(content))
    assert predict('退款',CATEGORIES,path,mapping_path=mapping)['source']=='rules'


@pytest.mark.parametrize('config',[{'C':float('nan')},{'max_iter':0},{'ngram_range':[3,1]},{'algorithm':'unapproved'}])
def test_bad_training_configuration_never_creates_an_artifact(tmp_path,config):
    data=_dataset(tmp_path/'train.jsonl',[('DEMO甲','a'),('DEMO乙','b')])
    with pytest.raises(ValueError):train(data,_source(tmp_path),tmp_path/'model.json',config=config)
    assert not (tmp_path/'model.json').exists()


def test_model_label_mapping_versions_and_manual_correction_remain_traceable(client,app,tmp_path):
    from conftest import login
    from sqlalchemy.orm import Session
    from app.models import Category
    data=_dataset(tmp_path/'training.jsonl',[('忘记密码登录','credential_reset'),('重置账号密码','credential_reset'),('用户登录失败','credential_reset'),('申请退款退费','refund_request'),('退款申请咨询','refund_request'),('退费办理','refund_request')])
    source=_source(tmp_path)
    with Session(app.state.engine) as db:
        db.add(Category(id=2,name='退款咨询',keywords='退款,退费',active=True,group_id=2));db.commit()
    def install(name,C,target):
        path=tmp_path/f'{name}.json';train(data,source,path,threshold=0.0,margin=0.0,config={'C':C})
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        mapping=tmp_path/f'{name}-map.json'
        mapping.write_text(json.dumps({'model_sha256':digest,'approved':True,'approved_by':'DEMO software fixture only','labels':{'credential_reset':target,'refund_request':2}}))
        app.state.model_path=path;app.state.expected_model_sha256=digest;app.state.label_map_path=mapping
        return path,digest,hashlib.sha256(mapping.read_bytes()).hexdigest()
    _,v1,m1=install('v1',1.0,1)
    login(client)
    first=client.post('/api/tickets',json={'title':'密码登录','description':'忘记密码登录'}).json()
    assert first['prediction_source']=='model' and first['category_id']==1
    assert first.get('prediction_label')=='credential_reset' and first.get('prediction_mapping_version')==m1
    login(client,'admin')
    corrected=client.post(f"/api/tickets/{first['id']}/actions",json={'version':first['version'],'action':'classify','category_id':2,'reason':'DEMO 人工纠错'}).json()
    assert corrected['category_id']==2 and corrected['assignee_id']==5
    assert corrected['prediction_label']=='credential_reset' and corrected['prediction_model_version']==v1
    path,v2,m2=install('v2',0.3,2)
    login(client)
    second=client.post('/api/tickets',json={'title':'密码登录','description':'忘记密码登录'}).json()
    assert second['prediction_model_version']==v2 and second['prediction_mapping_version']==m2
    assert second['category_id']==2 and v1!=v2 and m1!=m2
    assert client.get(f"/api/tickets/{first['id']}").json()['prediction_model_version']==v1
    altered=json.loads(path.read_text());altered['intercept'][0]+=1;path.write_text(json.dumps(altered))
    fallback=client.post('/api/tickets',json={'title':'密码问题','description':'密码'}).json()
    assert fallback['prediction_source']=='rules' and fallback['category_id']==1
    assert fallback['prediction_model_version'] is None


def test_new_database_and_directory_are_private(tmp_path):
    import os,stat
    from app.database import make_engine,migrate
    if os.name!='posix':pytest.skip('POSIX permission bits')
    path=tmp_path/'private-runtime'/'test.sqlite3'
    engine=make_engine(path)
    try:
        migrate(engine)
        assert stat.S_IMODE(path.parent.stat().st_mode)==0o700
        assert stat.S_IMODE(path.stat().st_mode)==0o600
    finally:engine.dispose()


def test_explicit_manual_mapping_and_foreign_model_mapping_fail_closed(tmp_path):
    model=_model();model['labels']=['refund_request','credential_reset']
    path=tmp_path/'model.json';path.write_text(json.dumps(model))
    mapping=tmp_path/'mapping.json'
    value={'model_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'approved':True,'approved_by':'DEMO fixture, not research approval','labels':{'refund_request':None,'credential_reset':2}}
    mapping.write_text(json.dumps(value))
    result=predict('退',CATEGORIES,path,mapping_path=mapping)
    assert result['source']=='model' and result['needs_manual'] and result['category_id'] is None
    assert result['predicted_label']=='refund_request' and result['model_version']==value['model_sha256']
    value['model_sha256']='0'*64;mapping.write_text(json.dumps(value))
    fallback=predict('退款',CATEGORIES,path,mapping_path=mapping)
    assert fallback['source']=='rules' and fallback['category_id']==1 and fallback['mapping_version'] is None


def test_training_cli_configuration_and_declared_evaluation_partition(tmp_path):
    import subprocess,sys
    root=Path(__file__).resolve().parents[2]
    source=_source(tmp_path)
    def partitioned(path,rows,partition):
        path.write_text('\n'.join(json.dumps({'text':text,'label':label,'source_partition':partition}) for text,label in rows))
        return path
    data=partitioned(tmp_path/'train.jsonl',[('DEMO 申请退款','refund'),('DEMO 退款办理','refund'),('DEMO 密码遗忘','account'),('DEMO 重设密码','account')],'train')
    config=tmp_path/'config.json';config.write_text(json.dumps({'ngram_range':[1,2],'C':0.5,'data_partition':'train'}))
    model=tmp_path/'model.json'
    run=subprocess.run([sys.executable,'-m','ml.train','--train',str(data),'--source',str(source),'--output',str(model),'--config',str(config)],cwd=root,capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    assert json.loads(run.stdout)['parameters']['C']==0.5
    testing=partitioned(tmp_path/'test.jsonl',[('DEMO 希望退费退款','refund'),('DEMO 需要找回密码','account')],'test')
    with pytest.raises(ValueError,match='分区'):
        evaluate(testing,source,model,tmp_path/'bad.json',data_partition='train')
    assert not (tmp_path/'bad.json').exists()
    report=evaluate(testing,source,model,tmp_path/'report.json',data_partition='test')
    assert report['test']['partitions']==['test'] and report['model_metadata']['training']['partitions']==['train']
    assert report['purpose']=='engineering_only_not_research_conclusion'
