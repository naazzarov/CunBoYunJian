import json
import httpx
from app import editorial, pipeline
from app.core import Cue


def test_dictionary_preserves_product_terms_and_quotes():
    cues=[Cue(1,4,'产品有使用场景。产品太贵怎么保存？')]
    result=editorial.keyword_analysis(cues)
    words={item['word']:item['count'] for item in result['top_keywords']}
    assert words['产品']==2 and words['使用场景']==1
    assert result['objection_candidates']==[{'start':1,'end':4,'quote':cues[0].text,'matched_terms':['太贵','怎么保存']}]
    assert len(result['lexicon_sha256'])==64


def test_seven_category_rejects_unknown_label_and_retries(monkeypatch):
    actual_client=httpx.Client
    requests=[]
    def respond(request):
        requests.append(json.loads(request.content))
        raw={'clips':[{'start_cue':1,'end_cue':1,'title':'产地介绍','reason':'完整介绍来源','category':'unknown' if len(requests)==1 else '产地溯源','score':80,'knowledge_ids':[1]}]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(raw)}}],'usage':{'total_tokens':12}})
    monkeypatch.setenv('LLM_JSON_SCHEMA','1')
    monkeypatch.setattr(pipeline.httpx,'Client',lambda **kw:actual_client(transport=httpx.MockTransport(respond),**kw))
    pipeline.TOKEN_USAGE.clear()
    clips,_=pipeline.select([Cue(0,4,'产品来自示例产地')],[{'id':1,'title':'来源规则','content':'来源描述需要证据','kind':'rule'}],{'min_seconds':3,'max_seconds':10,'max_clips':2,'segmentation_mode':'seven','output_language':'zh'})
    assert len(requests)==2 and clips[0]['category']=='产地溯源'
    schema=requests[0]['response_format']['json_schema']['schema']
    assert schema['properties']['clips']['items']['properties']['category']['enum']==editorial.SEVEN_ZH
    assert pipeline.TOKEN_USAGE==[{'total_tokens':12},{'total_tokens':12}]
    pipeline.TOKEN_USAGE.clear()


def test_short_candidates_trigger_correction_instead_of_silent_zero(monkeypatch):
    client=httpx.Client;requests=[]
    def respond(request):
        requests.append(json.loads(request.content))
        raw={'clips':[{'start_cue':1,'end_cue':1 if len(requests)==1 else 2,'title':'完整介绍','reason':'保留完整说明','category':'产品介绍','score':80,'knowledge_ids':[]}]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(raw)}}]})
    monkeypatch.setattr(pipeline.httpx,'Client',lambda **kw:client(transport=httpx.MockTransport(respond),**kw))
    pipeline.SELECTION_TRACE.clear()
    clips,_=pipeline.select([Cue(0,4,'开头'),Cue(4,20,'完整说明')],[],{'min_seconds':15,'max_seconds':30,'max_clips':2})
    assert len(requests)==2 and clips[0]['end']==20
    assert '4' in requests[1]['messages'][-1]['content']
    assert pipeline.SELECTION_TRACE[0]['duration_rejections'][0]['seconds']==4
    pipeline.SELECTION_TRACE.clear();pipeline.TOKEN_USAGE.clear()


def test_model_selects_only_offered_duration_valid_ranges(monkeypatch):
    client=httpx.Client;requests=[]
    def respond(request):
        body=json.loads(request.content);requests.append(body)
        menu=json.loads(body['messages'][1]['content'])['duration_valid_ranges']
        assert '1:1' not in menu and menu['1:2']==20
        schema=body['response_format']['json_schema']['schema']
        assert '1:1' not in schema['properties']['clips']['items']['properties']['range_id']['enum']
        raw={'clips':[{'range_id':'1:2','title':'完整介绍','reason':'保留完整说明','category':'产品介绍','score':80,'knowledge_ids':[]}]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(raw)}}]})
    monkeypatch.setenv('LLM_JSON_SCHEMA','1')
    monkeypatch.setattr(pipeline.httpx,'Client',lambda **kw:client(transport=httpx.MockTransport(respond),**kw))
    clips,_=pipeline.select([Cue(0,4,'开头'),Cue(4,20,'完整说明')],[],{'min_seconds':15,'max_seconds':30,'max_clips':2})
    assert len(requests)==1 and clips[0]['end']==20
    pipeline.SELECTION_TRACE.clear();pipeline.TOKEN_USAGE.clear()
