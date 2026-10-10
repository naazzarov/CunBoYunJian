"""Fixed seven-category policy and traceable keyword candidates."""
from collections import Counter
import hashlib
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent.parent
SEVEN_ZH=['信任背书','产地溯源','工艺制作','试吃体验','价格机制','消费场景','共富故事']
SEVEN_EN=['Trust endorsement','Origin tracing','Craftsmanship','Taste test','Pricing mechanism','Consumption scenario','Common-prosperity story']

def categories(config):
    return SEVEN_EN if config.get('output_language')=='en' else SEVEN_ZH

def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def keyword_analysis(cues):
    import jieba
    tokenizer=jieba.Tokenizer()
    tokenizer.load_userdict(str(ROOT/'lexicons/beef_jerky_lexicon.txt'))
    stop=set((ROOT/'lexicons/stopwords.txt').read_text().splitlines())
    counts=Counter(word.lower() for cue in cues for word in tokenizer.cut(cue.text)
                   if len(word)>1 and word not in stop and re.search(r'[\w\u4e00-\u9fff]',word))
    objections=['太贵','贵不贵','真假','保质期','配料','退货','不好吃','怎么保存']
    return {'top_keywords':[{'word':word,'count':count} for word,count in sorted(counts.items(),key=lambda x:(-x[1],x[0]))[:20]],
            'objection_candidates':[{'start':c.start,'end':c.end,'quote':c.text,'matched_terms':[w for w in objections if w in c.text]} for c in cues if any(w in c.text for w in objections)],
            'method':'jieba frequency; objection matches are review candidates, not verified findings',
            'lexicon_sha256':fingerprint(ROOT/'lexicons/beef_jerky_lexicon.txt')}
