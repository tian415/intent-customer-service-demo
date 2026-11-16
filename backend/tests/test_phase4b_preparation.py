"""Independent engineering samples only; no public dataset partition or research metrics."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import pytest
from ml.dataset import text_hash
from test_intent import _model, _source, _dataset


def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False)+'\n',encoding='utf-8');return path


def make_run(tmp_path):
    source=_source(tmp_path)
    rows={'train':[('北极北风','north','t1'),('北方寒风','north','t2'),('南海暖阳','south','t3'),('南方炎热','south','t4')],
          'validation':[('北星雪豹☃','north','v1'),('南岛海滩☃','south','v2')],
          'test':[('北地冰川☂','north','s1'),('南城热浪☂','south','s2')]}
    splits={}
    for name,items in rows.items():
        path=tmp_path/f'{name}.jsonl'
        path.write_text(''.join(json.dumps({'utterance':t,'intent':label,'thread':group},ensure_ascii=False)+'\n' for t,label,group in items),encoding='utf-8')
        splits[name]={'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'partition':None}
    config={'format':'ticket-run-v1','purpose':'engineering_preparation',
            'data':{'version':'test-v1','source':{'path':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()},
                    'text_field':'utterance','label_field':'intent','group_field':'thread','partition_field':None,'labels':['north','south']},
            'splits':splits,'model':{'parameters':{'ngram_range':[1,2],'max_features':200,'C':1.0,'max_iter':300,'random_state':17},'threshold':0.0,'margin':0.0},
            'leakage':{'similarity_threshold':0.9,'max_comparisons':100},'output':'result'}
    path=write_json(tmp_path/'config.json',config)
    return path,config


def test_run_config_fits_only_train_and_records_three_explicit_files(tmp_path):
    from ml.run import run
    path,config=make_run(tmp_path)
    before={p:p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    report=run(path)
    artifact=json.loads((tmp_path/'result/model.json').read_text())
    assert not any('☃' in k or '☂' in k for k in artifact['vocabulary'])
    assert artifact['metadata']['training']['samples']==4
    assert artifact['metadata']['parameters']['random_state']==17
    assert report['purpose']=='engineering_preparation' and report['data_version']=='test-v1'
    assert set(report['partitions'])=={'train','validation','test'}
    assert report['template_group_independence']=='not_certified'
    assert report['audit']['cross_split_near_complete']
    assert report['validation']['test']['samples']==2 and report['test']['test']['samples']==2
    assert all(p.read_bytes()==raw for p,raw in before.items())
    root=Path(__file__).resolve().parents[2]
    again=subprocess.run([sys.executable,'-m','ml.run','--config',str(path)],cwd=root,capture_output=True,text=True)
    assert again.returncode==2 and '存在' in again.stderr


@pytest.mark.parametrize('kind',['exact','group','near','incomplete','unknown_label','undeclared_group','undeclared_partition','version','sha'])
def test_run_stops_cross_partition_risks_before_creating_a_model(tmp_path,kind):
    from ml.run import run
    path,config=make_run(tmp_path)
    def edit(name,change):
        p=tmp_path/config['splits'][name]['path'];rows=[json.loads(line) for line in p.read_text().splitlines()]
        change(rows);p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
        config['splits'][name]['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    if kind=='exact':edit('validation',lambda rows:rows[0].update(utterance=' 北极北风 '))
    if kind=='group':edit('validation',lambda rows:rows[0].update(thread='t1'))
    if kind=='near':
        edit('train',lambda rows:rows[0].update(utterance='DEMO common text tide'))
        edit('validation',lambda rows:rows[0].update(utterance='DEMO common text diet'))
    if kind=='incomplete':config['leakage']['max_comparisons']=0
    if kind=='unknown_label':edit('validation',lambda rows:rows[0].update(intent='not_allowed'))
    if kind=='undeclared_group':
        config['data']['group_field']=None
        edit('validation',lambda rows:rows[0].update(group_id='known-but-undeclared'))
    if kind=='undeclared_partition':edit('validation',lambda rows:rows[0].update(source_partition='test'))
    if kind=='version':config['data']['version']='unconfirmed-version'
    if kind=='sha':config['splits']['test']['sha256']='0'*64
    write_json(path,config)
    with pytest.raises(ValueError):run(path)
    assert not (tmp_path/'result/model.json').exists()
    assert not (tmp_path/'result/completed.json').exists()


def test_near_audit_is_conservative_in_both_text_orders(tmp_path):
    from ml.audit import audit
    first=_dataset(tmp_path/'a.jsonl',[('DEMO common text tide','a')])
    second=_dataset(tmp_path/'b.jsonl',[('DEMO common text diet','a')])
    for splits in ({'train':first,'test':second},{'test':second,'train':first}):
        report=audit(splits,similarity_threshold=0.9,max_comparisons=1)
        assert report['near_duplicate_pairs']==1
        assert report['cross_split_near_duplicate_pairs']==1
        assert report['near_examples'][0]['similarity']==pytest.approx(0.904762)


def test_evaluation_metrics_include_manual_errors_and_pin_the_loaded_bytes(tmp_path,monkeypatch):
    import ml.evaluate as evaluation
    source=_source(tmp_path);model=_model()
    model['metadata']={'training':{'text_hashes':[text_hash('独立训练文本')],'group_hashes':[]}}
    path=write_json(tmp_path/'model.json',model);expected=hashlib.sha256(path.read_bytes()).hexdigest()
    data=_dataset(tmp_path/'test.jsonl',[('退','退款'),('无覆盖','账户'),('退申请','账户')])
    original=evaluation.model_choice
    def changed_file(text,loaded):
        changed={**model,'intercept':[0.5]};write_json(path,changed)
        return original(text,loaded)
    monkeypatch.setattr(evaluation,'model_choice',changed_file)
    report=evaluation.evaluate(data,source,path,tmp_path/'metrics.json')
    assert report['accuracy']==pytest.approx(1/3)
    assert report['macro_f1']==pytest.approx(1/3) and report['manual_count']==1
    assert report['classification_report']['账户']['support']==2
    assert report['model_sha256']==expected


@pytest.mark.parametrize('kind',['exact','group','near','allowed_but_unseen_label'])
def test_validation_test_boundary_is_checked_before_training(tmp_path,kind):
    from ml.run import run
    path,config=make_run(tmp_path)
    val=tmp_path/'validation.jsonl';test=tmp_path/'test.jsonl'
    validation=[json.loads(x) for x in val.read_text().splitlines()]
    testing=[json.loads(x) for x in test.read_text().splitlines()]
    if kind=='exact':testing[0]['utterance']=validation[0]['utterance']
    if kind=='group':testing[0]['thread']=validation[0]['thread']
    if kind=='near':
        validation[0]['utterance']='DEMO common text tide';testing[0]['utterance']='DEMO common text diet'
    if kind=='allowed_but_unseen_label':
        config['data']['labels'].append('new_intent');testing[0]['intent']='new_intent'
    for name,p,rows in [('validation',val,validation),('test',test,testing)]:
        p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
        config['splits'][name]['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    write_json(path,config)
    with pytest.raises(ValueError):run(path)
    report=json.loads((tmp_path/'result/preflight.json').read_text())
    assert report['blockers'] and not (tmp_path/'result/model.json').exists()


def test_explicit_original_partition_markers_are_preserved(tmp_path):
    from ml.run import run
    path,config=make_run(tmp_path);config['data']['partition_field']='source_partition'
    for name,spec in config['splits'].items():
        p=tmp_path/spec['path'];rows=[json.loads(x) for x in p.read_text().splitlines()]
        for row in rows:row['source_partition']=name
        p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
        spec['partition']=name;spec['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    write_json(path,config);report=run(path)
    assert report['validation']['test']['partitions']==['validation']
    assert report['test']['model_metadata']['training']['partitions']==['train']


@pytest.mark.parametrize('parameters',[None,{}, {'ngram_range':[1,2],'max_features':200,'C':1.0,'max_iter':300}])
def test_new_run_requires_explicit_model_parameters_and_random_seed(tmp_path,parameters):
    from ml.run import run
    path,config=make_run(tmp_path);config['model']['parameters']=parameters;write_json(path,config)
    with pytest.raises(ValueError,match='参数'):
        run(path)
    assert not (tmp_path/'result').exists()
