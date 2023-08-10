import os
import re
import csv
from omegaconf import DictConfig, OmegaConf
from typing import Optional, Set, List, Tuple, Union


RULES: List[List[Union[str, List[str]]]] = []
with open('rules/rule_j2i.csv', 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    for line in reader:
        line_:List[Union[str, List[str]]] = list(map(lambda x:x.split("|")if"|"in x else x, line))
        RULES.append(line_)
tone_rules:DictConfig = OmegaConf.load("rules/rule_tone.yaml")  # type: ignore

pron_format    = '^[a-z]{1,10}\\d{0,2}$'
#initial_format = '^(n[jg]?|bb?|dd?|[zcs][hrjl]?|[ptkg]h?|[hmqfvwjl])([wv]?)(?=[aeoiuymn])'
initial_format = '^(mb?|n[jrd]?|ngg?|[bdg]{1,2}|g[hn]?|r[bdgzscrh]|[zcs][hrjl]?|[ptkvw]h?|[hqfjlrx0])([jwv]?)(?=[aeoiuymn])'
coda_format    = "(?<=[aoreiwuy])(n[ng]?|[mptkh])(?=[0-9][0-9']?$)?"
tone_format    = "[0-9]?[0-9*][0-9']?$"
#vowel_format   = '^(ng$|m$|ii|uu|[iu][rw]?|[aeo][aorew]?|yw|yu$|y)'
vowel_format   = '(^ng?$|^m$|i[rwi]?|u[rwu]?|[aeo][aeowr]?|yu$|y)$'


jpp2ipa_ini = { 
"m":"m", "n":"n", "nj":"ȵ", "ng":"ŋ", 
"b":"p", "d":"t", "g":"k", "p":"pʰ", "t":"tʰ", "k":"kʰ", "q":"ʔ", 
"bb":"ɓ", "dd":"ɗ", 
"s":"s", "sh":"ʃ", "sr":"ʂ", "sj":"ɕ", 
"z":"ʦ", "zh":"ʧ", "zr":"ʈʂ", "zj":"ʨ", 
"c":"ʦʰ", "ch":"ʧʰ", "cr":"ʈʂʰ", "cj":"ʨʰ", 
"ph":"ɸ", "f":"f", "v":"v", "th":"θ", "h":"h", "w":"w", "j":"j", "sl":"ɬ", 
"zl":"tɬ", "cl":"tɬʰ", "l":"l", 
"gw":"kʷ", "kw":"kʷʰ", "hw":"hʷ",
"gv":"kᵛ", "kv":"kᵛʰ", "hv":"hᵛ"}
jpp2ipa_vow_obs = { "i":"i", "yu":"y", "y":"y", "ii":"ɿ", "uu":"ʉ", "ur":"ɯ", "u":"u", "iw":"ɪ", "yw":"ʏ", "uw":"ʊ", "ee":"e", "ew":"ø", "ir":"ɘ", "eo":"ɵ", "or":"ɤ", "oo":"o", "ea":"ə", "e":"ɛ", "oe":"œ", "aw":"ɜ", "ow":"ɞ", "er":"ʌ", "o":"ɔ", "ae":"æ", "a":"ɐ", "aa":"a", "ao":"ɶ", "ar":"ɑ", "oa":"ɒ", "m":"m̩", "n":"n̩", "ng":"ŋ̍", "z":"z" }
jpp2ipa_vow = {
    "i":"i", "yu":"y", "y":"y", "ur":"ɯ", "u":"u", "ee":"e", "eo":"ɵ", "oo":"o", "ea":"ə", "e":"ɛ", "oe":"œ", "o":"ɔ", "ae":"æ", "a":"ɐ", "aa":"a", "oa":"ɒ", "z":"z", "ii":"ɿ", "ew":"ø", "m":"m̩", "n":"n̩", "ng":"ŋ̍",}
jpp2ipa_cod_mark = { "m":"m̚", "n":"n̚", "ng":"ŋ̚", "p":"p̚", "t":"t̚", "k":"k̚", "h":"ʔ", "nn":"̃", "":""}
jpp2ipa_cod =  { "m":"m", "n":"n", "ng":"ŋ", "gn":"ɲ", "p":"p", "t":"t", "k":"k", "h":"ʔ", "nn":"̃", "":""}
# ii默认应该是/ɿ/  # 二選ɨ


# 将j++音节划分成声母、元音部分和辅音韵尾
# eg. splite_jpp('jat1') -> ['j', 'a', 't']
def splite_jpp(syllable: str) -> List[str]:
    ini = re.search(initial_format, syllable)
    cod = re.search(coda_format, syllable)
    ton = re.search(tone_format, syllable)
    ini = ini[0] if ini!=None else ''
    cod = cod[0] if cod!=None else ''
    ton = ton[0] if ton!=None else ''
    vows = syllable[len(ini):-(len(cod)+len(ton))] if cod!='' or ton!='' else syllable[len(ini):]
    syllable_splited = norm_jpp([ini, vows, cod, ton])
    return syllable_splited

# 正則化j++音節
def norm_jpp(splited: List[str]) -> List[str]:
    normed = splited.copy()
    if splited[0]=="0": normed[0] = "" # 0 -> 空
    if splited[0]!="" and len(splited[1])>=2:
        if (splited[1]in["ie"]and splited[2]!="")or splited[1]in["ieu"]:
            normed[1] = splited[1][1:] # iek -> ek, iet -> et, iep -> ep, ieu -> eu
        if splited[0][-1]=="j"  and (splited[1][0:2]in["ia","ie","io"]):
            normed[1] = splited[1][1:] # jia -> ja, njia -> nja, sjia -> sja
        if splited[0][-1]=="w"  and (splited[1][0:2]in["ua","ue","uo"]):
            normed[1] = splited[1][1:] # wua -> wa, kwua -> kwa
    return normed

# 按照rules.csv和默认规则将切分开的j++转为IPA
# eg. get_ipa([1, 2], ['j', 'a', 't', '1'], "廣州") -> ['j', ['ɐ'], 't', '5']
def get_ipa(locale_rules: List, splited: List[str], locale_name: str, info=None) -> Tuple[str, List[str], str, str]:
    locale_rules = [str(locale_rules_entry) for locale_rules_entry in locale_rules] + [locale_name]
    is_ini_transed = False
    is_vow_transed = False
    is_con_transed = False
    transed = ['', [], '', '']
    for i, entry in enumerate(RULES):
        if entry[0] not in locale_rules:
            continue
        if entry[1] != '*' and (entry[1]!=splited[0] if isinstance(entry[1], str) else splited[0] not in entry[1]):
            continue
        if entry[2] != '*' and (entry[2]!=splited[1] if isinstance(entry[2], str) else splited[1] not in entry[2]):
            continue
        if entry[3] != '*' and (entry[3]!=splited[2] if isinstance(entry[3], str) else splited[2] not in entry[3]):
            continue
        if entry[4] != '*' and not is_ini_transed:
            transed[0] = entry[4]
            is_ini_transed = True
        if entry[5] != '*' and not is_vow_transed:
            transed[1] = [entry[5]]   # 一定要有这个中括号，来保持返回格式统一
            is_vow_transed = True
        if entry[6] != '*' and not is_con_transed:
            transed[2] = entry[6]
            is_con_transed = True
    if not is_ini_transed:
        if splited[0] in jpp2ipa_ini:
            transed[0] = jpp2ipa_ini[splited[0]]
        elif "w"==splited[0][-1] and splited[0][:-1] in jpp2ipa_ini:
            transed[0] = jpp2ipa_ini[splited[0][:-1]] + "w"
        elif "v"==splited[0][-1] and splited[0][:-1] in jpp2ipa_ini:
            transed[0] = jpp2ipa_ini[splited[0][:-1]] + "v"
        else:
            transed[0] = jpp2ipa_ini[splited[0]]
    if not is_vow_transed:
        transed[1] = get_vows_ipa(splited[1])
    if not is_con_transed:
        transed[2] = jpp2ipa_cod[splited[2]]
    
    #print(splited[3])
    if splited[3] != "":
        checkedToneMark = "舒聲" if splited[2] not in ["p", "t", "k", "h"] else "入聲"
        tones_set = tone_rules[locale_name][checkedToneMark]
        tone_mark = splited[3]
        if tone_mark in tones_set:
            transed[3] = str(tones_set[tone_mark])
        elif splited[3].isdigit() and int(tone_mark) in tones_set:
            transed[3] = str(tones_set[int(tone_mark)])
        else:
            raise TypeError(f"調號不存在: {checkedToneMark}[{tone_mark}]")
    else:
        transed[3] = ""
    return tuple(transed)


# 将纯j++表示的元音串转成IPA
# eg. get_vows_ipa('yuyweyu') -> ['y', 'u', 'ʏ', 'ɛ', 'y']
def get_vows_ipa(vows: str) -> List[str]:
    ipa_vow_list = []
    while len(vows) != 0: #从前到后用正则检测元音 #現在是從後往前了 
        vow_ = re.search(vowel_format, vows)
        assert vow_ != None, f"元音不存在: {vows}"
        vow = vow_[0]
        ipa_vow_list.append(jpp2ipa_vow[vow])
        vows = vows[:-len(vow)]
    return ipa_vow_list[::-1]

# ['j', ['ɐ'], 't', '5'] -> "jɐt5"
def format_ipa(transed):
    return f"{transed[0]}{''.join(transed[1])}{transed[2]}{transed[3]}"