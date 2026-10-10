import pytest
from app.core import Cue
from app.roughcut import retained_ranges,rebase

def timeline():
    return {'version':'3','timebase':'24/1','v':[[{'offset':0,'dur':72},{'offset':312,'dur':72}]]}

def test_silence_mapping_and_protected_speech():
    cues=[Cue(1,2,'第一段'),Cue(13,15,'第二段')]
    spans=retained_ranges(timeline(),cues,16)
    assert spans==[(0,3),(13,16)]
    assert rebase(cues,spans)==[Cue(1,2,'第一段'),Cue(3,5,'第二段')]
    assert retained_ranges(timeline(),[Cue(2,14,'不能删掉这段语音')],16)==[(0,16)]

def test_speed_effects_fail_instead_of_misaligning_subtitles():
    value=timeline();value['v'][0][0]['effects']=['speed:2']
    with pytest.raises(ValueError,match='Speed'):retained_ranges(value,[],16)
