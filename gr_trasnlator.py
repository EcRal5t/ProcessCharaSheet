import os
import re
import csv
from typing import Optional, Set, List, Tuple, Union, Dict
from collections import defaultdict
from omegaconf import DictConfig, OmegaConf
ToneDictBase = Dict[int|str, int|str]
ToneDict = Dict[str, ToneDictBase]

class Term:
    b_i: str
    b_v: str
    b_c: str
    a_i: str
    a_v: str
    a_c: str
    imp: bool
    def __init__(self, l: Union[List[str], Tuple[str, ...]]):
        assert len(l)==6 or (len(l)==7 and l[-1]=="!"), f"len(l)={len(l)}, l={str(l)}"
        self.b_i, self.b_v, self.b_c, self.a_i, self.a_v, self.a_c = l[:6]
        self.imp = len(l)==7 and l[-1]=="!"
    def __repr__(self) -> str:
        return f"[{self.b_i},{self.b_v},{self.b_c} {'!'[:self.imp]}=> {self.a_i},{self.a_v},{self.a_c}]"
    def __str__(self) -> str:
        return self.__repr__()
        
class Rule:    
    i2i: Dict[str, List[Term]]
    i2j: Dict[str, List[Term]]
    j2i: Dict[str, List[Term]]
    j2j: Dict[str, List[Term]]
    tone_j2j: DictConfig
    tone_j2i: DictConfig
    base_path: str
    class Selected:
        i2i: List[Term]
        i2j: List[Term]
        j2i: List[Term]
        j2j: List[Term]
        tone_j2j: Dict[str, Dict[int|str, int|str]] = {}
        tone_j2i: Dict[str, Dict[int|str, int|str]] = {}
        tone_i2j: Dict[str, Dict[int|str, int|str]] = {}
        def tone_j2i_to_i2j(self):
            for k,v in self.tone_j2i.items():
                self.tone_i2j[k] = {v_:k_ for k_,v_ in v.items()}
        
    def read_config(self, base_path: str) -> str:
        self.base_path = base_path
        i2i_path = os.path.join(base_path, "rule_i2i.csv")
        i2j_path = os.path.join(base_path, "rule_i2j.csv")
        j2j_path = os.path.join(base_path, "rule_j2j.csv")
        j2i_path = os.path.join(base_path, "rule_j2i.csv")
        tone_j2j_path = os.path.join(base_path, "rule_tone_j2j.yaml")
        tone_j2i_path = os.path.join(base_path, "rule_tone_j2i.yaml")
        self.i2i, msg_1 = Rule.__read_csv(i2i_path)
        self.i2j, msg_2 = Rule.__read_csv(i2j_path)
        self.j2i, msg_3 = Rule.__read_csv(j2i_path)
        self.j2j, msg_4 = Rule.__read_csv(j2j_path)
        self.tone_j2j, msg_5 = Rule.__read_yml(tone_j2j_path)
        self.tone_j2i, msg_6 = Rule.__read_yml(tone_j2i_path)
        msg = "\n".join(filter(lambda x: x != "", [msg_1, msg_2, msg_3, msg_4, msg_5, msg_6]))
        return msg
    
    def reload(self) -> str:
        return self.read_config(self.base_path)
    
    def select(self, locate: str, append: List[Union[str,int]]) -> Tuple[Selected, str]:
        rule_seleted = Rule.Selected()
        rule_seleted.i2i, msg_i2i = self.__select_in_single_dict(locate, append, self.i2i)
        rule_seleted.i2j, msg_i2j = self.__select_in_single_dict(locate, append, self.i2j)
        rule_seleted.j2i, msg_j2i = self.__select_in_single_dict(locate, append, self.j2i)
        rule_seleted.j2j, msg_j2j = self.__select_in_single_dict(locate, append, self.j2j)
        rule_seleted.tone_j2j = self.tone_j2j.get(locate, OmegaConf.create())
        rule_seleted.tone_j2i = self.tone_j2i.get(locate, OmegaConf.create())
        rule_seleted.tone_j2i_to_i2j()
        msgs_ = [msg_i2i, msg_i2j, msg_j2i, msg_j2j]
        title = ["i2i", "i2j", "j2i", "j2j"]
        msgs  = [title+": "+msg_.strip() for title, msg_ in zip(title, msgs_) if msg_.strip() != ""]
        return rule_seleted, ", ".join(msgs)
    
    @staticmethod
    def __select_in_single_dict(locate: str, append: List[Union[str, int]], d: Dict[str, List[Term]]) -> Tuple[List[Term], str]:
        def __s(l: int|str, d: Dict[str, List[Term]]) -> Tuple[List[Term], str]:
            if l in d:
                return d[l], ""
            elif str(l) in d:
                return d[str(l)], ""
            else:
                return [], "No {}".format(l)
        r, msg = __s(locate, d)
        # msgs = [msg]
        for i in append:
            r_, _ = __s(i, d)
            r.extend(r_)
        return r, msg#"\n".join(msgs)
    
    @staticmethod
    def __read_csv(path: str) -> Tuple[Dict[str, List[Term]], str]:
        result: Dict[str, List[Term]] = defaultdict(list)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for line in reader:
                    if len(line) == 0: continue
                    _, line_ = Rule.__parse_csv_line(line[1:])
                    result[line[0]].extend(line_)
            msg = ""
        else:
            msg = "rule data not found: {}".format(path)
        return result, msg
    @staticmethod
    def __parse_csv_line(line: List[str]) -> Tuple[bool, List[Term]]:
        elements_split = [i.split('|') for i in line]
        seperator_count = [len(e)-1 for e in elements_split]
        seperator_count_filtered = list(filter(lambda x: x>0, seperator_count))
        if len(seperator_count_filtered)==0:
            return (True, [Term(line)])
        retrieve_loop_times = min(seperator_count_filtered)
        is_valid = retrieve_loop_times == max(seperator_count_filtered)
        elements_split_pad = [e+[e[-1]]*(retrieve_loop_times-len(e)+1) for e in elements_split]
        # return ["".join([e[i] for e in elements_split_pad]) for i in range(retrieve_loop_times+1)]
        terms = [Term(i) for i in zip(*elements_split_pad)]
        return (is_valid, terms)
    @staticmethod
    def __read_yml(path: str) -> Tuple[DictConfig, str]:
        if os.path.exists(path):
            r = OmegaConf.load(path)
            assert isinstance(r, DictConfig)
            msg = ""
        else:
            r = OmegaConf.create()
            msg = "TONE RULE FILE NOT FOUND AT: {} !".format(path)
        return r, msg

RULE = Rule()
RULE.read_config(os.path.join(os.path.dirname(__file__), "rules"))

pron_format    = '^[a-z]{1,10}\\d{0,2}$'
initial_format = '^(mb?|n[jrd]?|ngg?|[bdg]{1,2}|g[hn]?|r[bdgzscrh]|[zcs][hrjl]?|[ptkvw]h?|[hqfjlrx0])([jwv]?)(?=[aeoiuymn])'
coda_format    = "(?<=[aoreiwuy])(n[ng]?|[mptkh])(?=[0-9][0-9']?$)?"
tone_format    = "[0-9]?[0-9*][0-9']?$"
vowel_format   = '(^ng?$|^m$|i[rwi]?|u[rwu]?|[aeo][aeowr]?|yu$|y)$'

jpp2ipa_ini = { "":"", 
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
jpp2ipa_vow = { # ii默认应该是/ɿ/  # 二選ɨ
    "i":"i", "yu":"y", "y":"y", "ur":"ɯ", "u":"u", "ee":"e", "eo":"ɵ", "oo":"o", "ea":"ə", "e":"ɛ", "oe":"œ", "o":"ɔ", "ae":"æ", "a":"ɐ", "aa":"a", "oa":"ɒ", "z":"z", "ii":"ɿ", "ew":"ø", "m":"m̩", "n":"n̩", "ng":"ŋ̍",}
jpp2ipa_cod_mark = { "m":"m̚", "n":"n̚", "ng":"ŋ̚", "p":"p̚", "t":"t̚", "k":"k̚", "h":"ʔ", "nn":"̃", "":""}
jpp2ipa_cod =  { "m":"m", "n":"n", "ng":"ŋ", "gn":"ɲ", "p":"p", "t":"t", "k":"k", "h":"ʔ", "nn":"̃", "":""}


# 将j++音节划分成声母、元音部分和辅音韵尾
# eg. split_jpp('jat1') -> (('j', 'a', 't'), '1')
def split_jpp(syllable: str) -> Tuple[Tuple[str, str, str], str]:
    ini = re.search(initial_format, syllable)
    cod = re.search(coda_format, syllable)
    ton = re.search(tone_format, syllable)
    ini = ini[0] if ini!=None else ''
    cod = cod[0] if cod!=None else ''
    ton = ton[0] if ton!=None else ''
    vows = syllable[len(ini):-(len(cod)+len(ton))] if cod!='' or ton!='' else syllable[len(ini):]
    syllable_splited = norm_jpp((ini, vows, cod))
    return ((ini, vows, cod), ton)

# 正則化j++音節
def norm_jpp(splited: Tuple[str, str, str]) -> Tuple[str, str, str]:
    ini, vows, cod = splited
    if splited[0]=="0": ini = "" # 0 -> 空
    if splited[0]!="" and len(splited[1])>=2:
        if (splited[1]in["ie"]and splited[2]!="")or splited[1]in["ieu"]:
            vows = splited[1][1:] # iek -> ek, iet -> et, iep -> ep, ieu -> eu
        if splited[0][-1]=="j"  and (splited[1][0:2]in["ia","ie","io"]):
            vows = splited[1][1:] # jia -> ja, njia -> nja, sjia -> sja
        if splited[0][-1]=="w"  and (splited[1][0:2]in["ua","ue","uo"]):
            vows = splited[1][1:] # wua -> wa, kwua -> kwa
    return (ini, vows, cod)

# 按照傳入的規則将切分开的j++转为IPA
# eg. pron_translate(轉換規則, ['j', 'a', 't']) -> ['j', 'ɐ', 't']
# to_jpp_or_ipa -> True: 轉換為j++音節
# to_jpp_or_ipa -> False: 轉換為IPA
# to_jpp_or_ipa -> None: 不轉換
def pron_translate(*, rules: List[Term], inp: Tuple[str, str, str], to_jpp_or_ipa: Optional[bool]) -> Tuple[str, str, str]:
    # if "ŋ̍" in inp[1]:
    #     print("break point")
    ini_transed: Optional[str] = None
    vow_transed: Optional[str] = None
    con_transed: Optional[str] = None
    # transed: List[Optional[str]] = [None, None, None]
    for i, entry in enumerate(rules):
        if entry.b_i != '*' and (entry.b_i!=inp[0] and (to_jpp_or_ipa is not None or entry.b_i!=ini_transed)):
            continue
        if entry.b_v != '*' and (entry.b_v!=inp[1] and (to_jpp_or_ipa is not None or entry.b_v!=vow_transed)):
            continue
        if entry.b_c != '*' and (entry.b_c!=inp[2] and (to_jpp_or_ipa is not None or entry.b_c!=con_transed)):
            continue
        if entry.a_i != '*' and (entry.imp or ini_transed is None):
            ini_transed = entry.a_i
        if entry.a_v != '*' and (entry.imp or vow_transed is None):
            vow_transed = entry.a_v
        if entry.a_c != '*' and (entry.imp or con_transed is None):
            con_transed = entry.a_c
    if to_jpp_or_ipa is None:
        if ini_transed is None:
            ini_transed = inp[0]
        if vow_transed is None:
            vow_transed = inp[1]
        if con_transed is None:
            con_transed = inp[2]
    else:
        if ini_transed is None:
            if to_jpp_or_ipa:
                ini_transed = ipa2jpp_ini[inp[0]]
            else:
                if False and inp[0] not in jpp2ipa_ini and inp[0][-1] == "w" and inp[0][:-1] in jpp2ipa_ini:
                    ini_transed = jpp2ipa_ini[inp[0][:-1]] + "ʷ" # ngw -> ŋʷ, sw -> sʷ, fw -> fʷ ...
                else:
                    ini_transed = jpp2ipa_ini[inp[0]]
        if vow_transed is None:
            vow_transed = get_vows_jpp(inp[1]) if to_jpp_or_ipa else get_vows_ipa(inp[1])
        if con_transed is None:
            con_transed = ipa2jpp_cod[inp[2]] if to_jpp_or_ipa else jpp2ipa_cod[inp[2]]
    return (ini_transed, vow_transed, con_transed)


def tone_translate(*, rules: ToneDictBase, tone_mark: str, skippable:bool=False) -> str:
    transed = ""
    if tone_mark in rules:
        transed = str(rules[tone_mark])
    elif tone_mark.isdigit() and int(tone_mark) in rules:
        transed = str(rules[int(tone_mark)])
    elif skippable:
        transed = tone_mark
    elif tone_mark == "":
        raise ValueError(f"調號爲空")
    else:
        raise ValueError(f"調號不存在: [{tone_mark}] 在 {rules} 內")
    return transed

# 将纯j++表示的元音串转成IPA
# eg. get_vows_ipa('yuyweyu') -> 'yuʏɛy'
def get_vows_ipa(vows: str) -> str:
    ipa_vow_list = []
    while len(vows) != 0: #从前到后用正则检测元音 #現在是從後往前了 
        vow_ = re.search(vowel_format, vows)
        assert vow_ != None, f"元音不存在: {vows}"
        vow = vow_[0]
        ipa_vow_list.append(jpp2ipa_vow[vow])
        vows = vows[:-len(vow)]
    return "".join(ipa_vow_list[::-1])

ipa2jpp_ini = { v:k for k,v in jpp2ipa_ini.items() }
ipa2jpp_ini.update({"kw":"gw", "kwh":"kw", "hw":"hw", "kʰʷ":"kw"})
ipa2jpp_ini.update({"kv":"gv", "kvh":"kv", "hv":"hv", "kʰᵛ":"kv"})
ipa2jpp_ini.update({"ts":"z", "tsʰ":"c", "tsh":"c"})
ipa2jpp_ini.update({"ʃ":"sh", "tʃ":"zh", "tʃʰ":"ch", "tʃh":"ch"})
ipa2jpp_ini.update({"ɕ":"sj", "tɕ":"zj", "tɕʰ":"cj", "tɕh":"cj"})
ipa2jpp_vow = { v:k for k,v in jpp2ipa_vow.items() }
ipa2jpp_vow.update({"m":"m", "n":"n", "ŋ":"ng"})
ipa2jpp_cod = { v:k for k,v in jpp2ipa_cod.items() }
ipa2jpp_cod.update({ v:k for k,v in jpp2ipa_cod_mark.items() })

ipa_tone_format = '(\\d*)$'
ipa_vows_format = '([iyɯueɵoəɛøœɔæɐaɒɿɪʊ]+|ŋ̩|n̩|m̩|ŋ̍)'
ipa_coda_format = '([(mnŋptk)̚?]?|ʔ?)$'

# 将 IPA 音节划分成辅音声母、元音和辅音韵尾
# eg. split_ipa('jat1') -> ['j', 'a', 't']
def split_ipa(syllable: str) -> Tuple[Tuple[str, str, str], str]:
    # if syllable == "0ŋ̩22":
    #     True==True
    
    tone = re.search(ipa_tone_format, syllable)
    tone = "" if tone is None else tone[0]
    if len(tone) > 0: syllable = syllable[:-len(tone)]
    
    coda = re.search(ipa_coda_format, syllable)
    coda = "" if coda is None else coda[0]
    if len(coda) > 0: syllable = syllable[:-len(coda)]
    
    vows = re.search(ipa_vows_format, syllable)
    if vows == None:
        if coda in "mnŋ":
            vows, coda = coda, ""
        else:
            assert False, f"元音不存在: {syllable}"
    else:
        vows = vows[0]
    init = syllable[:-len(vows)]
    return ((init, vows, coda), tone)

def get_vows_jpp(vows: str) -> str:
    jpp_vow_list = [ipa2jpp_vow[vow] for vow in vows]
    return "".join(jpp_vow_list)