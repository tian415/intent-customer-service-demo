"""Synthetic DEMO data only: no imported public corpus or research choice."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]


def source_file(path):
    path.write_text(json.dumps({'name':'DEMO engineering fixture','url':'local:pytest','license':'synthetic fixture only','version':'fixture-1','approved_by':'automated fixture; not a research approval','usage_approved':True,'privacy_reviewed':True}))
    return path


def write_rows(path, rows):
    path.write_text('\n'.join(json.dumps(row,ensure_ascii=False) for row in rows)+'\n')
    return path


def test_prepare_explicit_mapping_preserves_original_text_partition_and_input(tmp_path):
    from ml.prepare import prepare
    data=write_rows(tmp_path/'raw.jsonl',[
        {'id':'shared-1','locale':'zh-CN','partition':'train','utt':'  ＡＢＣ 原始文本  ','intent':'source_a'},
        {'id':'shared-2','locale':'zh-CN','partition':'test','utt':'另一个原始文本','intent':'source_b'},
    ])
    original=data.read_bytes()
    labels=tmp_path/'labels.json';labels.write_text('["业务甲","业务乙"]')
    mapping=tmp_path/'mapping.json';mapping.write_text('{"source_a":"业务甲","source_b":"业务乙"}')
    output=tmp_path/'prepared.jsonl'
    report=prepare(data,source_file(tmp_path/'source.json'),output,labels,text_field='utt',label_field='intent',mapping_path=mapping,partition_field='partition',partition='train',group_field='id')
    rows=[json.loads(line) for line in output.read_text().splitlines()]
    assert rows==[{'text':'  ＡＢＣ 原始文本  ','label':'业务甲','group_id':'shared-1','source_row':1,'source_partition':'train'}]
    assert data.read_bytes()==original
    assert report['input_sha256']==hashlib.sha256(original).hexdigest()
    assert report['samples']==1 and report['label_counts']=={'业务甲':1}
    assert report['partition']=='train' and report['automatic_split'] is False
    assert json.loads(output.with_suffix('.jsonl.manifest.json').read_text())==report
    with pytest.raises(ValueError,match='存在'):
        prepare(data,source_file(tmp_path/'source.json'),output,labels,text_field='utt',label_field='intent')


def test_prepare_unknown_labels_duplicate_keys_and_duplicate_text_fail_before_output(tmp_path):
    from ml.prepare import prepare
    labels=tmp_path/'labels.json';labels.write_text('["approved"]')
    source=source_file(tmp_path/'source.json')
    output=tmp_path/'out.jsonl'
    for rows in ([{'text':'未知标签','label':'unapproved'}], [{'text':'ABC','label':'approved'},{'text':'ＡＢＣ','label':'approved'}]):
        data=write_rows(tmp_path/'raw.jsonl',rows)
        with pytest.raises(ValueError):prepare(data,source,output,labels)
        assert not output.exists() and not output.with_suffix('.jsonl.manifest.json').exists()
    data=write_rows(tmp_path/'raw.jsonl',[{'text':'原文','label':'approved'}])
    with pytest.raises(ValueError,match='原始|输入'):
        prepare(data,source,data,labels)
    assert json.loads(data.read_text())['text']=='原文'


def test_clinc_import_selects_only_the_explicit_original_partition(tmp_path):
    from ml.prepare import prepare
    data=tmp_path/'clinc.json';data.write_text(json.dumps({'train':[['DEMO first','a']], 'oos_train':[['DEMO unknown','oos']]}))
    labels=tmp_path/'labels.json';labels.write_text('["a"]')
    output=tmp_path/'out.jsonl'
    prepare(data,source_file(tmp_path/'source.json'),output,labels,format='clinc',partition='train')
    assert json.loads(output.read_text())['label']=='a'
    assert 'unknown' not in output.read_text()


def test_audit_reports_exact_conflicting_near_and_group_leakage_without_raw_text(tmp_path):
    from ml.audit import audit
    first=write_rows(tmp_path/'train.jsonl',[{'text':'退款申请ABCDEFGHIJK','label':'甲','group_id':'conversation-1'}, {'text':'重复句','label':'甲'}, {'text':'重复句','label':'乙'}])
    second=write_rows(tmp_path/'test.jsonl',[{'text':'退款申请ABCDEFGHIJL','label':'甲','group_id':'conversation-1'}, {'text':'重复句','label':'甲'}])
    before={p:p.read_bytes() for p in [first,second]}
    report=audit({'train':first,'test':second},similarity_threshold=0.85,max_comparisons=100)
    assert report['splits']['train']['samples']==3
    assert report['exact_duplicate_groups']==1 and report['cross_split_exact_groups']==1
    assert report['label_conflict_groups']==1 and report['cross_split_group_groups']==1
    assert report['near_duplicate_pairs']>=1 and report['near_complete'] is True
    assert '退款申请ABCDEFGHIJK' not in json.dumps(report,ensure_ascii=False)
    assert all(p.read_bytes()==content for p,content in before.items())
    limited=audit({'train':first,'test':second},similarity_threshold=0.85,max_comparisons=0)
    assert limited['near_complete'] is False and limited['compared_pairs']==0
    assert limited['cross_split_exact_groups']==1


def test_prepare_and_audit_commands_are_standard_library_only(tmp_path):
    data=write_rows(tmp_path/'input.jsonl',[{'text':'DEMO 唯一文本','label':'a'}])
    labels=tmp_path/'labels.json';labels.write_text('["a"]')
    output=tmp_path/'prepared.jsonl'
    result=subprocess.run([sys.executable,'-S','-m','ml.prepare','--input',str(data),'--source',str(source_file(tmp_path/'source.json')),'--output',str(output),'--labels',str(labels)],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    report=tmp_path/'audit.json'
    result=subprocess.run([sys.executable,'-S','-m','ml.audit','--split',f'train={output}','--output',str(report)],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(report.read_text())['splits']['train']['samples']==1


def test_bounded_near_audit_prioritizes_cross_split_leakage_candidates(tmp_path):
    from ml.audit import audit
    training=write_rows(tmp_path/'train.jsonl',[{'text':'DEMO 退款 ABCDEFGHIJ','label':'a'},{'text':'DEMO 天气 无关内容','label':'b'}])
    testing=write_rows(tmp_path/'test.jsonl',[{'text':'DEMO 退款 ABCDEFGHIK','label':'a'}])
    result=audit({'train':training,'test':testing},similarity_threshold=0.85,max_comparisons=1)
    assert result['near_duplicate_pairs']==1
    assert result['cross_split_compared_pairs']==1
    assert result['cross_split_total_pairs']==2 and result['cross_split_near_complete'] is False
    assert result['near_examples'][0]['first']['split']!=result['near_examples'][0]['second']['split']


def test_audit_reads_original_field_names_without_rewriting_or_losing_duplicates(tmp_path):
    from ml.audit import audit
    original=tmp_path/'published.csv'
    original.write_text('flags,instruction,category,intent,response\nB,Refund please,REFUND,get_refund,unused\nZ,REFUND PLEASE,REFUND,get_refund,unused too\n',encoding='utf-8')
    before=original.read_bytes()
    report=audit({'published':original},text_field='instruction',label_field='intent',max_comparisons=5)
    assert report['splits']['published']['samples']==2
    assert report['splits']['published']['label_counts']=={'get_refund':2}
    assert report['exact_duplicate_groups']==1 and report['label_conflict_groups']==0
    assert original.read_bytes()==before
    with pytest.raises(ValueError,match='text/label|字段'):
        audit({'published':original},text_field='missing',label_field='intent')
