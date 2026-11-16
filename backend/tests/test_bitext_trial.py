"""Synthetic source-shaped fixtures; actual public run is recorded separately."""
import csv
import hashlib
import json
from pathlib import Path
import pytest


def test_trial_runs_existing_import_model_and_ticket_boundaries_without_touching_input(tmp_path):
    from scripts.bitext_trial import run_trial
    labels=['recover_password','get_refund','delivery_options']
    rows=[]
    for label,phrase in zip(labels,['password reset','refund request','delivery choices']):
        for suffix in ['alpha','beta','gamma']:
            rows.append({'flags':'B','instruction':f'{phrase} {phrase} {suffix}','category':label.upper(),'intent':label,'response':'fixture only, not public data'})
    raw=tmp_path/'source.csv'
    with raw.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    original=raw.read_bytes()
    source=tmp_path/'source.json';source.write_text(json.dumps({'name':'synthetic trial regression only','url':'local:pytest','license':'synthetic fixture','version':'test','approved_by':'test fixture only','usage_approved':True,'privacy_reviewed':True}))
    report=run_trial(raw,source,tmp_path/'trial',per_intent=2,near_limit=20)
    assert raw.read_bytes()==original
    assert report['input_sha256']==hashlib.sha256(original).hexdigest()
    assert report['sample_count']==6 and report['label_count']==3
    assert report['integration']['account']['prediction_label']=='recover_password'
    assert report['integration']['account']['category_name']=='账号问题'
    assert report['integration']['unmapped']['needs_manual']
    assert report['integration']['damaged_english']['needs_manual']
    assert report['integration']['damaged_chinese']['prediction_source']=='rules'
    correction=report['integration']['manual_correction']
    assert correction['category_name']=='退款咨询' and correction['prediction_label']=='recover_password'
    assert correction['prediction_model_version']==report['model_sha256']
    assert report['formal_split'] is None and not report['holdout_evaluation']
    assert 'accuracy' not in report
    with pytest.raises(ValueError,match='存在'):
        run_trial(raw,source,tmp_path/'trial',per_intent=2,near_limit=20)


def test_trial_refuses_label_conflicts_before_selecting_a_convenient_subset(tmp_path):
    from scripts.bitext_trial import run_trial
    rows=[{'flags':'B','instruction':'same conflicting instruction','category':'REFUND','intent':'get_refund','response':'fixture'},
          {'flags':'B','instruction':'SAME CONFLICTING INSTRUCTION','category':'ACCOUNT','intent':'recover_password','response':'fixture'},
          {'flags':'B','instruction':'delivery only alpha','category':'DELIVERY','intent':'delivery_options','response':'fixture'},
          {'flags':'B','instruction':'delivery only beta','category':'DELIVERY','intent':'delivery_options','response':'fixture'}]
    for intent,phrase in [('get_refund','refund request'),('recover_password','password reset')]:
        for suffix in ('alpha','beta'):
            rows.append({'flags':'B','instruction':f'{phrase} {suffix}','category':intent,'intent':intent,'response':'fixture'})
    raw=tmp_path/'conflict.csv'
    with raw.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    source=tmp_path/'source.json';source.write_text(json.dumps({'name':'synthetic conflict','url':'local:test','license':'fixture','version':'test','approved_by':'test only','usage_approved':True,'privacy_reviewed':True}))
    with pytest.raises(ValueError,match='标签冲突'):
        run_trial(raw,source,tmp_path/'trial',per_intent=2)
    assert not (tmp_path/'trial'/'engineering-subset.csv').exists()
