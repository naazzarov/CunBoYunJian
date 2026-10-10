import pytest
from app.core import Cue,parse_srt,srt,retrieve,validate_plan,windows

TEXT='1\n00:00:01,250 --> 00:00:03,750\nOne useful point.\n\n2\n00:00:04,000 --> 00:00:07,000\nIts complete answer.\n'

def test_srt_roundtrip_and_rebase():
    cues=parse_srt(TEXT,8)
    assert parse_srt(srt(cues))==cues
    result=parse_srt(srt(cues,2,5))
    assert result==[Cue(0,1.75,'One useful point.'),Cue(2,3,'Its complete answer.')]

@pytest.mark.parametrize('text',[
    'nonsense',
    '1\n00:00:02,000 --> 00:00:01,000\nBackwards',
    '1\n00:00:01,000 --> 00:00:02,000\n',
    '1\n00:00:03,000 --> 00:00:04,000\nLater\n\n2\n00:00:00,000 --> 00:00:02,000\nEarlier'
])
def test_bad_subtitles_rejected(text):
    with pytest.raises(ValueError): parse_srt(text)

def test_subtitles_beyond_duration_rejected():
    with pytest.raises(ValueError): parse_srt(TEXT,4)

def test_chinese_retrieval_and_editorial_rules():
    cards=[{'id':1,'title':'牛肉干产地','content':'牛肉干来自塔城','kind':'fact'}, {'id':2,'title':'Rules','content':'Never misrepresent claims','kind':'rule'},{'id':3,'title':'Weather','content':'Sunny morning','kind':'fact'}]
    assert [c['id'] for c in retrieve('塔城牛肉干',cards)]==[2,1]

def plan(a=1.25,b=7):
    return {'clips':[{'start':a,'end':b,'title':'Useful answer','reason':'Complete explanation','category':'Q&A','score':85,'knowledge_ids':[1]}]}

@pytest.mark.parametrize('a,b',[(True,7),(-1,7),(1,float('nan')),(1,90),(6,4)])
def test_hallucinated_times_rejected(a,b):
    with pytest.raises(ValueError): validate_plan(plan(a,b),parse_srt(TEXT),8,3,90,6)

def test_duration_limit_and_overlap():
    p=plan();p['clips']*=2
    assert len(validate_plan(p,parse_srt(TEXT),8,3,90,6))==1
    assert validate_plan(p,parse_srt(TEXT),8,10,90,6)==[]

def test_chunking_preserves_original_absolute_times():
    cues=[Cue(i*100,i*100+80,str(i)) for i in range(12)]
    chunks=list(windows(cues,max_seconds=250))
    assert len(chunks)==6
    assert [c for chunk in chunks for c in chunk]==cues

def test_arbitrary_mid_sentence_times_rejected():
    with pytest.raises(ValueError): validate_plan(plan(2.5,6),parse_srt(TEXT),8,3,90,6)

def test_model_cue_ids_resolve_to_exact_source_times():
    from app.core import resolve_cue_plan
    cues=parse_srt(TEXT)
    p=resolve_cue_plan({'clips':[{'start_cue':1,'end_cue':2,'title':'Answer'}]},cues)
    assert p['clips'][0]['start']==1.25 and p['clips'][0]['end']==7
    with pytest.raises(ValueError): resolve_cue_plan({'clips':[{'start_cue':1,'end_cue':99}]},cues)


def test_duration_menu_and_range_ids_preserve_absolute_boundaries():
    from app.core import duration_ranges,resolve_cue_plan
    cues=[Cue(100,104,'开头'),Cue(104,114.42,'说明'),Cue(114.42,120,'完整结尾'),Cue(140,145,'另一个话题')]
    ranges=duration_ranges(cues,15,25)
    assert '1:2' not in ranges and '1:3' in ranges
    assert all(15<=cues[b-1].end-cues[a-1].start<=25 for a,b in ranges.values())
    result=resolve_cue_plan({'clips':[{'range_id':'1:3','title':'完整介绍'}]},cues,ranges)
    assert result['clips'][0]['start']==100 and result['clips'][0]['end']==120
    with pytest.raises(ValueError):resolve_cue_plan({'clips':[{'range_id':'1:2'}]},cues,ranges)
    assert duration_ranges(cues,60,90)=={}
