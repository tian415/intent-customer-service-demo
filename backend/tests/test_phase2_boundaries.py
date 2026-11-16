"""Independent Phase 2 engineering regressions; no research data or metrics."""
import json
import pytest
from ml.dataset import read_dataset, read_source
from ml.evaluate import evaluate


def test_duplicate_csv_headers_and_unlabelled_values_are_rejected(tmp_path):
    path=tmp_path/'ambiguous.csv'
    path.write_text('text,text,label\n原始文本,被覆盖文本,a\n')
    with pytest.raises(ValueError, match='重复.*列|列.*重复'):
        read_dataset(path)
    path.write_text('text,label\n原始文本,a,多余值\n')
    with pytest.raises(ValueError, match='列|字段'):
        read_dataset(path)


def test_source_duplicate_approval_key_is_rejected(tmp_path):
    path=tmp_path/'source.json'
    path.write_text('{"name":"DEMO","url":"local:test","license":"fixture","version":"test","approved_by":"fixture only","usage_approved":false,"usage_approved":true,"privacy_reviewed":true}')
    with pytest.raises(ValueError, match='重复'):
        read_source(path)


def test_invalid_model_provenance_is_a_validation_error_not_an_attribute_error(tmp_path):
    from test_intent import _model, _source, _dataset
    model=_model()
    model['metadata']=['invalid object']
    model_path=tmp_path/'model.json'
    model_path.write_text(json.dumps(model))
    data=_dataset(tmp_path/'test.jsonl',[('退款申请','退款')])
    with pytest.raises(ValueError, match='元信息|metadata'):
        evaluate(data,_source(tmp_path),model_path,tmp_path/'report.json')
    assert not (tmp_path/'report.json').exists()


def test_model_identity_is_the_digest_of_the_actual_loaded_bytes(tmp_path):
    import hashlib
    from ml.intent import predict
    from test_intent import _model, CATEGORIES
    path=tmp_path/'model.json'
    path.write_text(json.dumps(_model()))
    first=predict('退',CATEGORIES,path)
    assert first.get('model_version')==hashlib.sha256(path.read_bytes()).hexdigest()
    assert first['source']=='model'
    path.write_text(json.dumps(_model(),indent=2))
    second=predict('退',CATEGORIES,path)
    assert second.get('model_version')!=first['model_version']
    path.write_text('broken')
    fallback=predict('退款',CATEGORIES,path)
    assert fallback['source']=='rules' and fallback.get('model_version') is None


def test_declared_conversation_groups_cannot_cross_training_and_evaluation(tmp_path):
    from ml.train import train
    from test_intent import _source
    training=tmp_path/'train.jsonl'
    rows=[{'text':'DEMO 退款申请','label':'退款','group_id':'shared'}, {'text':'DEMO 密码问题','label':'账户','group_id':'another'}]
    training.write_text('\n'.join(json.dumps(row) for row in rows))
    model=tmp_path/'model.json'
    source=_source(tmp_path)
    train(training,source,model)
    test=tmp_path/'test.jsonl'
    test.write_text(json.dumps({'text':'DEMO 原对话的另一个不同轮次','label':'退款','group_id':'shared'}))
    with pytest.raises(ValueError,match='分组|会话'):
        evaluate(test,source,model,tmp_path/'report.json')
    assert not (tmp_path/'report.json').exists()


def test_actual_trained_model_routes_and_persists_version_while_broken_model_falls_back(client,app,tmp_path):
    import hashlib
    from sqlalchemy.orm import Session
    from app.models import Category, Ticket
    from conftest import login
    from ml.train import train
    from test_intent import _source, _dataset
    data=_dataset(tmp_path/'train.jsonl',[('登录密码','账号问题'),('重置账号密码','账号问题'),('忘记登录密码','账号问题'),('申请退款','退款咨询'),('退款退费申请','退款咨询'),('退费咨询','退款咨询')])
    model=tmp_path/'model.json'
    train(data,_source(tmp_path),model,threshold=0.0,margin=0.0)
    digest=hashlib.sha256(model.read_bytes()).hexdigest()
    with Session(app.state.engine) as db:
        db.add(Category(id=2,name='退款咨询',keywords='退款,退费',active=True,group_id=2))
        db.commit()
    app.state.model_path=model
    login(client)
    first=client.post('/api/tickets',json={'title':'登录密码','description':'登录密码'}).json()
    assert first['prediction_source']=='model' and first['category_id']==1 and first['assignee_id']==3
    assert first.get('prediction_model_version')==digest
    model.write_text('corrupt artifact')
    second=client.post('/api/tickets',json={'title':'密码问题','description':'密码'}).json()
    assert second['prediction_source']=='rules' and second['category_id']==1
    assert second.get('prediction_model_version') is None
    assert any('模型不可用' in event['detail'] for event in second['events'])
    with Session(app.state.engine) as db:
        assert db.get(Ticket,first['id']).prediction_model_version==digest
    assert client.get(f"/api/tickets/{first['id']}").json()['prediction_model_version']==digest


def test_customer_role_cannot_change_until_owned_tickets_close(client,app):
    from fastapi.testclient import TestClient
    from conftest import login
    login(client)
    ticket=client.post('/api/tickets',json={'title':'密码问题','description':'DEMO 角色变更保护'}).json()
    staff=TestClient(app,headers={'X-Requested-With':'ticket-ui'})
    try:
        login(staff,'admin')
        payload={'display_name':'测试用户','role':'agent','active':True,'group_id':1}
        for role in ('agent','admin'):
            denied=staff.put('/api/admin/users/1',json={**payload,'role':role,'group_id':1 if role=='agent' else None})
            assert denied.status_code==409 and '未关闭' in denied.json()['detail']
            assert client.get('/api/auth/me').json()['user']['role']=='user'
            assert client.get(f"/api/tickets/{ticket['id']}").json()['owner_id']==1
        login(staff,'agent')
        processing=staff.post(f"/api/tickets/{ticket['id']}/actions",json={'version':ticket['version'],'action':'accept'}).json()
        resolved=staff.post(f"/api/tickets/{ticket['id']}/actions",json={'version':processing['version'],'action':'resolve','reason':'账号已恢复'}).json()
        login(staff,'admin')
        assert staff.put('/api/admin/users/1',json=payload).status_code==409
        closed=client.post(f"/api/tickets/{ticket['id']}/actions",json={'version':resolved['version'],'action':'close'})
        assert closed.status_code==200 and closed.json()['status']=='closed'
        assert staff.put('/api/admin/users/1',json=payload).status_code==200
        assert client.get('/api/auth/me').status_code==401
        assert login(client)['role']=='agent'
    finally:
        staff.close()


def test_malformed_csv_header_is_a_safe_validation_error(tmp_path):
    path=tmp_path/'bad-header.csv'
    path.write_text('"unterminated,text,label\n')
    with pytest.raises(ValueError,match='CSV.*格式'):
        read_dataset(path)
