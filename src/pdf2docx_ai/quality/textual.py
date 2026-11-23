"""Exact, located text diagnostics with explicit harmless normalization."""
from bisect import bisect_left
from collections import Counter
import re
import unicodedata
from rapidfuzz.distance import Levenshtein
from .metrics import text_metrics

NORMALIZATION_PROFILE='NFC; whitespace; typographic ff/fi/fl/ffi/ffl/st ligatures; soft-hyphen/BOM/zero-width-space removal; case, accents, real hyphens, punctuation and numeric signs preserved'
_LIGATURES=str.maketrans({'ﬀ':'ff','ﬁ':'fi','ﬂ':'fl','ﬃ':'ffi','ﬄ':'ffl','ﬅ':'st','ﬆ':'st','\u00ad':'','\ufeff':'','\u200b':''})
MM_PER_PT=25.4/72


def normalize_text(text):
    return ' '.join(unicodedata.normalize('NFC',text).translate(_LIGATURES).split())


def _location(word):
    if word is None:return None
    return {'page':word['page'],'bbox_pt':word['bbox'],'bbox_mm':[v*MM_PER_PT for v in word['bbox']],
            'text':word['text'],'word_id':word.get('id',f"{word['page']}:{word['index']}")}


def _indexed_text(words):
    pieces=[];owners=[]
    for word in words:
        text=normalize_text(word['text'])
        if not text:continue
        if pieces:pieces.append(' ');owners.append(None)
        pieces.append(text);owners.extend([word]*len(text))
    return ''.join(pieces),owners


def _order_stats(pairs):
    ranks=[j for i,j in sorted(pairs)];tails=[]
    for j in ranks:
        pos=bisect_left(tails,j)
        if pos==len(tails):tails.append(j)
        else:tails[pos]=j
    # Exact inversion count, O(n log n), avoiding quadratic repeated-token lists.
    tree=[0]*(max(ranks,default=-1)+3);inversions=0
    for seen,value in enumerate(ranks):
        k=value+1;prefix=0
        while k:prefix+=tree[k];k-=k&-k
        inversions+=seen-prefix;k=value+1
        while k<len(tree):tree[k]+=1;k+=k&-k
    n=len(ranks)
    return {'matched_words':n,'inversions':inversions,'inversion_fraction':inversions/(n*(n-1)/2) if n>1 else 0.,
            'longest_ordered_subsequence':len(tails),'ordered_fraction':len(tails)/n if n else None,
            'note':'Order of one-to-one exact word anchors; repeated-token identity is geometric and heuristic.'}


def analyze_text(source_words,target_words,*,logical_source=None,logical_target=None,docx_body_text=None,
                 source_body=None,ground_truth=None,ground_truth_hypothesis=None,limit=250):
    from .visual_diff import _match_tokens
    reference,ref_owners=_indexed_text(source_words);hypothesis,hyp_owners=_indexed_text(target_words)
    raw_ref=' '.join(w['text'] for w in source_words);raw_hyp=' '.join(w['text'] for w in target_words)
    strict=text_metrics(raw_ref,raw_hyp) if source_words else {'cer':None,'wer':None}
    normalized=text_metrics(reference,hypothesis) if source_words else {'cer':None,'wer':None}
    normalized.update(profile=NORMALIZATION_PROFILE,reference='normalized native PDF stream order')
    pairs=_match_tokens([{**w,'text':normalize_text(w['text'])} for w in source_words],
                        [{**w,'text':normalize_text(w['text'])} for w in target_words])
    matched_s={i for i,j in pairs};matched_t={j for i,j in pairs}
    unmatched_s=[_location(w) for i,w in enumerate(source_words) if i not in matched_s]
    unmatched_t=[_location(w) for j,w in enumerate(target_words) if j not in matched_t]
    source_counts=Counter(normalize_text(w['text']) for w in source_words)
    duplicates=[_location(w) for j,w in enumerate(target_words) if j not in matched_t and normalize_text(w['text']) in source_counts]
    operations=[];op_count=0;op_totals=Counter()
    if source_words:
        edits=Levenshtein.editops(reference,hypothesis,processor=None);op_count=len(edits)
        for edit in edits:
            op_totals[edit.tag]+=1
            if len(operations)<limit:
                operations.append({'operation':edit.tag,'source_offset':edit.src_pos,'target_offset':edit.dest_pos,
                    'source_character':reference[edit.src_pos] if edit.tag!='insert' else '',
                    'target_character':hypothesis[edit.dest_pos] if edit.tag!='delete' else '',
                    'source':_location(ref_owners[edit.src_pos]) if edit.src_pos<len(ref_owners) else None,
                    'target':_location(hyp_owners[edit.dest_pos]) if edit.dest_pos<len(hyp_owners) else None})
    chars_s=Counter(''.join(reference.split()));chars_t=Counter(''.join(hypothesis.split()))
    count_only_equal=chars_s==chars_t
    normalized_only=(strict.get('cer') or 0)>0 and normalized.get('cer')==0
    raw_order=_order_stats(pairs)
    logical={};body={}
    if logical_source is not None and logical_target is not None and logical_source:
        logical=text_metrics(normalize_text(' '.join(w['text'] for w in logical_source)),
                             normalize_text(' '.join(w['text'] for w in logical_target)))
        logical.update(reference='inferred physical PDF flow; not semantic ground truth',status='measured_heuristic')
    if docx_body_text is not None and source_body:
        body=text_metrics(normalize_text(' '.join(w['text'] for w in source_body)),normalize_text(docx_body_text))
        body.update(reference='inferred PDF body reading flow versus visible DOCX XML body order; headers/footers measured separately',status='measured_heuristic')
    numeric=lambda s:re.findall(r'[+−-]?\d+(?:[.,:/−-]\d+)*%?',s)
    nums_s=[];nums_t=[]
    for words,records in ((source_words,nums_s),(target_words,nums_t)):
        for word in words:
            for token in numeric(normalize_text(word['text'])):records.append((token,word))
    ns=Counter(n for n,w in nums_s);nt=Counter(n for n,w in nums_t)
    missing=ns-nt;extra=nt-ns
    numeric_pairs=_match_tokens([{**w,'text':value} for value,w in nums_s],[{**w,'text':value} for value,w in nums_t])
    numeric_s={i for i,j in numeric_pairs};numeric_t={j for i,j in numeric_pairs}
    result={'status':'measured' if source_words else 'unavailable_no_native_reference','strict_stream':strict,
        'normalized_stream':normalized,'normalization_only_difference':normalized_only,
        'logical_pdf_flow':logical,'docx_body_order':body,'stream_order':raw_order,
        'missing_characters':sum((chars_s-chars_t).values()),'added_characters':sum((chars_t-chars_s).values()),
        'non_whitespace_character_counts_equal':count_only_equal,
        'sequence_error_interpretation':'normalization_only' if normalized_only else 'order_or_tokenization' if count_only_equal and normalized.get('cer') else 'content_or_sequence_difference',
        'sequence_edit_count':op_count,'sequence_edit_counts':dict(op_totals),'sequence_edit_locations':operations,
        'missing_token_count':len(unmatched_s),'added_token_count':len(unmatched_t),'potential_duplicate_token_count':len(duplicates),
        'missing_token_locations':unmatched_s[:limit],'added_token_locations':unmatched_t[:limit],'potential_duplicate_locations':duplicates[:limit],
        'numbers_dates':{'missing_count':sum(missing.values()),'added_count':sum(extra.values()),
                         'missing':dict(missing),'added':dict(extra),
                         'missing_locations':[{'value':v,**_location(w)} for i,(v,w) in enumerate(nums_s) if i not in numeric_s][:limit],
                         'added_locations':[{'value':v,**_location(w)} for j,(v,w) in enumerate(nums_t) if j not in numeric_t][:limit]},
        'location_limit':limit,'locations_truncated':max(len(unmatched_s),len(unmatched_t),op_count)>limit,
        'location_note':'Coordinates are containing native word boxes, not per-glyph boundaries. Edit operations describe the declared sequence reference, not proof of semantic deletion; tokenization/order and character deficits remain separate.'}
    if ground_truth is not None:
        result['ground_truth']=text_metrics(normalize_text(ground_truth),normalize_text(ground_truth_hypothesis if ground_truth_hypothesis is not None else raw_hyp))
        result['ground_truth']['reference']='external reference order versus target physical flow; whitespace/typographic normalization explicit'
    return result
