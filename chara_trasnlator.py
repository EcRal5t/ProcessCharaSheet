# filename: chara_translator.py

import os
import re
import csv
from typing import Optional, Set, List, Tuple, Union, Dict
from collections import defaultdict
from omegaconf import DictConfig, OmegaConf

# 定义声调字典的基础类型，键和值可以是整数或字符串。
ToneDictBase = Dict[int|str, int|str]

# 定义声调字典的类型，键为方言地点名称。
ToneDict = Dict[str, ToneDictBase]

class Term:
    """
    表示一条具体的转换规则。
    
    每个 Term 对象代表从一个音素组合（声母、韵母、韵尾）到另一个的映射。
    例如：在某个方言中，声母 v 在韵母 o 前，发音变为 ɔ。
    
    Attributes:
        b_i (str): 转换前的声母 (before initial)
        b_v (str): 转换前的韵母 (before vowel)
        b_c (str): 转换前的韵尾 (before coda)
        a_i (str): 转换后的声母 (after initial)
        a_v (str): 转换后的韵母 (after vowel)
        a_c (str): 转换后的韵尾 (after coda)
        imp (bool): 是否为重要规则 (important)。若为 True，则此规则具有更高优先级，会覆盖其他非重要规则的结果。
    """
    b_i: str
    b_v: str
    b_c: str
    a_i: str
    a_v: str
    a_c: str
    imp: bool
    def __init__(self, l: Union[List[str], Tuple[str, ...]]):
        """
        根据传入的列表或元组初始化规则。
        列表长度应为6或7。第7个元素若为"!"，则标记为重要规则。
        """
        assert len(l)==6 or (len(l)==7 and l[-1]=="!"), f"len(l)={len(l)}, l={str(l)}"
        self.b_i, self.b_v, self.b_c, self.a_i, self.a_v, self.a_c = l[:6]
        self.imp = len(l)==7 and l[-1]=="!"
    def __repr__(self) -> str:
        """返回规则的字符串表示形式，方便调试。"""
        return f"[{self.b_i},{self.b_v},{self.b_c} {'!'[:self.imp]}=> {self.a_i},{self.a_v},{self.a_c}]"
    def __str__(self) -> str:
        return self.__repr__()
        
class Rule:
    """
    管理所有音韵转换规则的加载、选择和重载。
    
    这个类会从指定的规则文件夹中读取CSV（音节部分）和YAML（声调）文件，
    并能根据指定的方言地点（locate）和附加规则（append）来筛选出当前需要应用的规则集。
    """
    i2i: Dict[str, List[Term]] # IPA to IPA
    i2j: Dict[str, List[Term]] # IPA to Jyutping
    j2i: Dict[str, List[Term]] # Jyutping to IPA
    j2j: Dict[str, List[Term]] # Jyutping to Jyutping
    tone_j2j: DictConfig
    tone_j2i: DictConfig
    base_path: str
    class Selected:
        """一个嵌套类，用于存放根据方言地点选择出的特定规则集。"""
        i2i: List[Term]
        i2j: List[Term]
        j2i: List[Term]
        j2j: List[Term]
        tone_j2j: Dict[str, Dict[int|str, int|str]] = {}
        tone_j2i: Dict[str, Dict[int|str, int|str]] = {}
        tone_i2j: Dict[str, Dict[int|str, int|str]] = {}
        def tone_j2i_to_i2j(self):
            """将 J2I (Jyutping到IPA) 的声调规则反转，生成 I2J (IPA到Jyutping) 的规则。"""
            for k,v in self.tone_j2i.items():
                self.tone_i2j[k] = {v_:k_ for k_,v_ in v.items()}
        
    def read_config(self, base_path: str) -> str:
        """
        从指定的基础路径读取所有规则和配置文件。
        
        Args:
            base_path (str): 包含所有 .csv 和 .yaml 规则文件的目录。
            
        Returns:
            str: 包含加载状态或错误信息的字符串。
        """
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
        """重新加载所有规则文件。"""
        return self.read_config(self.base_path)
    
    def select(self, locate: str, append: List[Union[str,int]]) -> Tuple[Selected, str]:
        """
        根据方言地点和其他附加规则，从总规则库中筛选出适用的规则子集。
        
        Args:
            locate (str): 主要的方言地点名称，如 "新會" or "廣州"。
            append (List[Union[str,int]]): 需要附加的通用规则集名称，如 [0, 1]。
            
        Returns:
            Tuple[Selected, str]: 一个包含已选规则的 Selected 对象和一条操作信息。
        """
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
        """在一个规则字典中，根据地点和附加键名来抽取规则列表。"""
        def __s(l: int|str, d: Dict[str, List[Term]]) -> Tuple[List[Term], str]:
            # 优先匹配原始键，然后尝试匹配字符串化的键
            if l in d:
                return d[l], ""
            elif str(l) in d:
                return d[str(l)], ""
            else:
                return [], "No {}".format(l)
            
        # 首先获取主要地点的规则
        r, msg = __s(locate, d)
        # 然后追加所有附加规则集中的规则
        for i in append:
            r_, _ = __s(i, d)
            r.extend(r_)
        return r, msg#"\n".join(msgs)
    
    @staticmethod
    def __read_csv(path: str) -> Tuple[Dict[str, List[Term]], str]:
        """
        读取并解析一个CSV格式的规则文件。

        CSV格式说明:
        - 第一列是地点标识（如 "新會", "廣州", "1"）。
        - 之后各列定义了一条或多条规则。
        - 使用 "|" 可以在一列中定义多个并行的元素，用于生成多条规则（见 __parse_csv_line）。
        - 例子: `新會,*,io,k|ng,*,iø,*` 会被解析成两条规则。
        """
        result: Dict[str, List[Term]] = defaultdict(list)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for line in reader:
                    if len(line) == 0: continue
                    # 解析CSV行，一行可能包含多条规则
                    _, line_ = Rule.__parse_csv_line(line[1:])
                    # 按地点标识存储规则
                    result[line[0]].extend(line_)
            msg = ""
        else:
            msg = "rule data not found: {}".format(path)
        return result, msg
    
    @staticmethod
    def __parse_csv_line(line: List[str]) -> Tuple[bool, List[Term]]:
        """
        解析CSV文件中的单行数据，这行数据可能通过 '|' 符号定义了多条规则。
        
        该方法能将 `a|b, x, c|d` 这样的输入，转置成 `(a,x,c)` 和 `(b,x,d)` 两条独立的规则。
        如果某列元素少于其他列，则会用该列的最后一个元素进行填充。
        """
        # 按 '|' 分割每一列
        elements_split = [i.split('|') for i in line]
        seperator_count = [len(e)-1 for e in elements_split]
        seperator_count_filtered = list(filter(lambda x: x>0, seperator_count))
        
        # 如果没有'|'，说明只是一条简单规则
        if len(seperator_count_filtered)==0:
            return (True, [Term(line)])
        
        # 确定由'|'定义的并行规则数量
        retrieve_loop_times = min(seperator_count_filtered)
        is_valid = retrieve_loop_times == max(seperator_count_filtered)
        
        # 对元素数量不足的列进行填充
        elements_split_pad = [e+[e[-1]]*(retrieve_loop_times-len(e)+1) for e in elements_split]
        
        # 通过 zip(*...) 实现矩阵转置，将列数据变成行数据，从而生成多条Term对象
        terms = [Term(i) for i in zip(*elements_split_pad)]
        return (is_valid, terms)
    
    @staticmethod
    def __read_yml(path: str) -> Tuple[DictConfig, str]:
        """读取并解析 YAML 格式的声调规则文件。"""
        if os.path.exists(path):
            r = OmegaConf.load(path)
            assert isinstance(r, DictConfig)
            msg = ""
        else:
            r = OmegaConf.create()
            msg = "TONE RULE FILE NOT FOUND AT: {} !".format(path)
        return r, msg

# 全局规则实例，在模块加载时自动读取配置
RULE = Rule()
RULE.read_config(os.path.join(os.path.dirname(__file__), "rules"))

# --- Jyutping 音节结构解析与转换 ---

# 用于解析 Jyutping 音节的正则表达式
pron_format    = '^[a-z]{1,10}\\d{0,2}$'
# 声母正则：匹配所有可能的粤拼声母
initial_format = '^(mb?|n[jrd]?|ngg?|[bdg]{1,2}|g[hn]?|r[bdgzscrh]|[zcs][hrjl]?|[ptkvw]h?|[hqfjlrx0])([jwv]?)(?=[aeoiuymn])'
# 韵尾正则：在元音后匹配可能的韵尾
coda_format    = "(?<=[aoreiwuy])(n[ng]?|[mptkh])(?=[\\d`*]|$)"
# 声调正则：匹配结尾的数字声调
tone_format    = "[0-9]?[0-9*][0-9']?(`\\d+)?$"
# 韵母/元音正则：匹配核心元音部分
vowel_format   = '(^ng?$|^m$|i[rwi]?|u[rwu]?|[aeo][aeowr]?|yu$|y)$'

# --- 默认的 Jyutping (j++) 到 IPA 的转换表 ---
# 声母 j++ -> IPA
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
"gv":"kᵛ", "kv":"kᵛʰ", "hv":"hᵛ",
"rh":"ɦ",
}
# 韵母 j++ -> IPA
jpp2ipa_vow = {
    "i":"i", "yu":"y", "y":"y", "ur":"ɯ", "u":"u", "ee":"e", "eo":"ɵ", "oo":"o", "ea":"ə", "e":"ɛ", "oe":"œ", "o":"ɔ", "ae":"æ", "a":"ɐ", "aa":"a", "oa":"ɒ", "z":"z", "ir":"ɿ", "ew":"ø", "m":"m̩", "n":"n̩", "ng":"ŋ̍"}
# 韵尾 j++ -> IPA (带标记)
jpp2ipa_cod_mark = { "m":"m̚", "n":"n̚", "ng":"ŋ̚", "p":"p̚", "t":"t̚", "k":"k̚", "h":"ʔ", "nn":"̃", "":""}
# 韵尾 j++ -> IPA (不带标记)
jpp2ipa_cod =  { "m":"m", "n":"n", "ng":"ŋ", "gn":"ɲ", "p":"p", "t":"t", "k":"k", "h":"ʔ", "nn":"̃", "":""}



def split_jpp(syllable: str, norm: bool=False) -> Tuple[Tuple[str, str, str], str]:
    """
    将一个完整的Jyutping音节（带声调）切分为 (声母, 韵母, 韵尾) 和 声调。

    Args:
        syllable (str): 待切分的Jyutping音节，如 "jyut6"。
        norm (bool, optional): 是否对切分后的音节进行正规化。默认为 False。

    Returns:
        Tuple[Tuple[str, str, str], str]: ((声母, 韵母, 韵尾), 声调)。
                                           例如: split_jpp('jat1') -> (('j', 'a', 't'), '1')
    """
    ini = re.search(initial_format, syllable)
    cod = re.search(coda_format, syllable)
    ton = re.search(tone_format, syllable)
    ini = ini[0] if ini!=None else ''
    cod = cod[0] if cod!=None else ''
    ton = ton[0] if ton!=None else ''
    vows = syllable[len(ini):-(len(cod)+len(ton))] if cod!='' or ton!='' else syllable[len(ini):]
    syllable_splited = norm_jpp((ini, vows, cod)) if norm else (ini, vows, cod)
    return (syllable_splited, ton)

# 正則化j++音節
def norm_jpp(splited: Tuple[str, str, str]) -> Tuple[str, str, str]:
    """
    对切分后的Jyutping音节进行正规化处理。
    例如处理一些介音和声母合并的情况: 'jia' -> 'ja', 'wua' -> 'wa'。

    Args:
        splited (Tuple[str, str, str]): (声母, 韵母, 韵尾)

    Returns:
        Tuple[str, str, str]: 正规化后的 (声母, 韵母, 韵尾)。
    """
    ini, vows, cod = splited
    if splited[0]=="0": ini = "" # 0 -> 空
    if splited[0]!="" and len(splited[1])>=2:
        if (splited[1]in["ie"]and splited[2]!="")or splited[1]in["ieu"]:
            vows = splited[1][1:] # iek -> ek, iet -> et, iep -> ep, ieu -> eu
        if splited[0][-1]=="j"  and (splited[1][:2]in["ia","ie","io"]or(splited[1]in["io"]and splited[2]!="")):
            vows = splited[1][1:] # jia -> ja, njia -> nja, sjia -> sja
        if splited[0][-1]=="w"  and (splited[1][:2]in["ua","ue","uo"]or(splited[1]in["ui"]and splited[2]!="")):
            vows = splited[1][1:] # wua -> wa, kwua -> kwa
    return (ini, vows, cod)


def pron_translate(*, rules: List[Term], inp: Tuple[str, str, str], to_jpp_or_ipa: Optional[bool]) -> Tuple[str, str, str]:
    """
    根据传入的规则列表，对一个已切分的音节进行翻译。

    Args:
        rules (List[Term]): 要应用的规则列表。
        inp (Tuple[str, str, str]): (声母, 韵母, 韵尾) 形式的输入音节。
        to_jpp_or_ipa (Optional[bool]): 转换方向。
                                       - True: 转换为 Jyutping (IPA -> j++)
                                       - False: 转换为 IPA (j++ -> IPA)
                                       - None: 不进行默认转换，仅应用规则。

    Returns:
        Tuple[str, str, str]: 翻译后的 (声母, 韵母, 韵尾)。
    """
    ini_transed: Optional[str] = None
    vow_transed: Optional[str] = None
    con_transed: Optional[str] = None
    
    # 遍历所有规则进行匹配
    for i, entry in enumerate(rules):
        if entry.b_i != '*' and (entry.b_i!=inp[0] and (to_jpp_or_ipa is not None or entry.b_i!=ini_transed)):
            continue
        if entry.b_v != '*' and (entry.b_v!=inp[1] and (to_jpp_or_ipa is not None or entry.b_v!=vow_transed)):
            continue
        if entry.b_c != '*' and (entry.b_c!=inp[2] and (to_jpp_or_ipa is not None or entry.b_c!=con_transed)):
            continue
        
        # 匹配成功，应用规则的'after'部分进行转换。
        # 重要规则(imp)会直接覆盖，非重要规则仅在尚未转换时生效。
        if entry.a_i != '*' and (entry.imp or ini_transed is None):
            ini_transed = entry.a_i
        if entry.a_v != '*' and (entry.imp or vow_transed is None):
            vow_transed = entry.a_v
        if entry.a_c != '*' and (entry.imp or con_transed is None):
            con_transed = entry.a_c
            
    # 如果规则应用后某些部分仍未被转换，则使用默认的转换方案。
    if to_jpp_or_ipa is None: # 只应用规则，不进行默认转换
        if ini_transed is None:
            ini_transed = inp[0]
        if vow_transed is None:
            vow_transed = inp[1]
        if con_transed is None:
            con_transed = inp[2]
    else: # 进行默认转换
        if ini_transed is None:
            if to_jpp_or_ipa: # IPA -> j++
                ini_transed = ipa2jpp_ini[inp[0]]
            else: # j++ -> IPA
                # 处理带w介音的特殊情况，如 ngw -> ŋʷ
                if inp[0] not in jpp2ipa_ini and inp[0][-1] == "w" and inp[0][:-1] in jpp2ipa_ini:
                    ini_transed = jpp2ipa_ini[inp[0][:-1]] + "ʷ" # ngw -> ŋʷ, sw -> sʷ, fw -> fʷ ...
                else:
                    ini_transed = jpp2ipa_ini[inp[0]]
        if vow_transed is None:
            vow_transed = get_vows_jpp(inp[1]) if to_jpp_or_ipa else get_vows_ipa(inp[1])
        if con_transed is None:
            con_transed = ipa2jpp_cod[inp[2]] if to_jpp_or_ipa else jpp2ipa_cod[inp[2]]
    return (ini_transed, vow_transed, con_transed)


def tone_translate(*, rules: ToneDictBase, tone_mark: str, skippable:bool=False) -> str:
    """
    根据声调规则字典转换声调。

    Args:
        rules (ToneDictBase): 声调转换规则，一个字典。
        tone_mark (str): 原始声调标记 (如 '1', '6')。
        skippable (bool, optional): 如果为True，当找不到规则时，直接返回原声调。默认为 False。

    Raises:
        ValueError: 如果找不到声调规则且 `skippable` 为 False。

    Returns:
        str: 转换后的声调。
    """
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


def get_vows_ipa(vows: str) -> str:
    """
    将纯Jyutping表示的元音串（可能包含多个元音组合）转换为IPA。
    例如: get_vows_ipa('eoy') -> 'ɵy'

    Args:
        vows (str): Jyutping元音字符串。

    Returns:
        str: 转换后的IPA元音字符串。
    """
    ipa_vow_list = []
    # 从后向前贪心匹配最长的元音单元
    while len(vows) != 0:
        vow_ = re.search(vowel_format, vows)
        assert vow_ != None, f"元音不存在: {vows}"
        vow = vow_[0]
        ipa_vow_list.append(jpp2ipa_vow[vow])
        vows = vows[:-len(vow)]
    # 因为是倒序匹配的，所以需要反转回来
    return "".join(ipa_vow_list[::-1])

# --- 反向转换 (IPA -> j++) 的常量和函数 ---

# 通过反转 j++ -> IPA 字典来创建 IPA -> j++ 字典
ipa2jpp_ini = { v:k for k,v in jpp2ipa_ini.items() }
# 更新一些多对一或不明确的映射
ipa2jpp_ini.update({"kw":"gw", "kwh":"kw", "hw":"hw", "kʰʷ":"kw"})
ipa2jpp_ini.update({"kv":"gv", "kvh":"kv", "hv":"hv", "kʰᵛ":"kv"})
ipa2jpp_ini.update({"ts":"z", "tsʰ":"c", "tsh":"c"})
ipa2jpp_ini.update({"ʃ":"sh", "tʃ":"zh", "tʃʰ":"ch", "tʃh":"ch"})
ipa2jpp_ini.update({"ɕ":"sj", "tɕ":"zj", "tɕʰ":"cj", "tɕh":"cj"})
ipa2jpp_vow = { v:k for k,v in jpp2ipa_vow.items() }
ipa2jpp_vow.update({"m":"m", "n":"n", "ŋ":"ng"})
ipa2jpp_vow.update({"ʌ": "a", "ɑ": "aa"})
ipa2jpp_cod = { v:k for k,v in jpp2ipa_cod.items() }
ipa2jpp_cod.update({ v:k for k,v in jpp2ipa_cod_mark.items() })

# --- IPA 音节结构的正则表达式 ---
ipa_tone_format = '(\\d*)$'
ipa_vows_format = '([iyɯueɵoɤəɛøœɔæɐaɑɒʌɿɪʊᵃ]+|ŋ̩|n̩|m̩|ŋ̍)'
ipa_coda_format = '([(mnŋptk)̚?]?|ʔ?)$'

# 将 IPA 音节划分成辅音声母、元音和辅音韵尾
# eg. split_ipa('jat1') -> ['j', 'a', 't']
def split_ipa(syllable: str) -> Tuple[Tuple[str, str, str], str]:
    """
    将一个完整的IPA音节（带声调）切分为 (声母, 韵母, 韵尾) 和 声调。
    这是 split_jpp 的反向操作。

    Args:
        syllable (str): 待切分的IPA音节，如 "jɐt5"。

    Returns:
        Tuple[Tuple[str, str, str], str]: ((声母, 韵母, 韵尾), 声调)。
    """
    # 从后往前依次切分声调、韵尾、韵母
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
    """
    将IPA元音字符串转换为Jyutping表示。
    这是 get_vows_ipa 的反向操作。

    Args:
        vows (str): IPA元音字符串。

    Returns:
        str: 转换后的Jyutping元音字符串。
    """
    # IPA元音通常是单字符，直接逐个查找替换即可
    jpp_vow_list = [ipa2jpp_vow[vow] for vow in vows]
    return "".join(jpp_vow_list)
