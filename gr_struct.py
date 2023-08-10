# encoding: utf-8
# python3
import pandas as pd
import opencc
import time
import logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s | %(funcName)s: %(levelname)s] %(message)s')

from typing import Optional, Any, List, Tuple, Dict, Callable, Union

from gr_trasnlator import *

class Chara:
    chara : str
    status: int = 0
    index : int = 0
    class Pron:
        prons: List[str]
        mean: str
        ipas: List[str]
        def __init__(self, prons: List[str], mean: str, ipas: List[str]):
            self.prons = prons
            self.mean  = mean
            self.ipas  = ipas
        def __eq__(self, __o: object) -> bool:
            if not isinstance(__o, Chara.Pron): return False
            if any([p in __o.prons for p in self.prons]) and (self.mean!="" and self.mean==__o.mean): return True
            if all([p in __o.prons for p in self.prons]) or all([p in self.prons for p in __o.prons]): return True
            return False
        def norm_and_to_ipa(self, norm_rule: List[Term], pron_rule: List[Term], tone_rule: Dict):
            split_prons = sorted([split_jpp(p) for p in self.prons], key=lambda x:x[0][1]+x[0][2])
            jpps: List[str] = []
            ipas: List[str] = []
            for pron_, tone_ in split_prons:
                pron_jpp = pron_translate(rules=norm_rule, inp=pron_, to_jpp_or_ipa=None)
                pron_ipa = pron_translate(rules=pron_rule, inp=pron_jpp, to_jpp_or_ipa=False)
                checked_tone_mark = "舒聲" if pron_[2] not in ["p", "t", "k", "h"] else "入聲"
                tone = tone_translate(rules=tone_rule[checked_tone_mark], tone_mark=tone_)
                jpps.append(pron_jpp[0]+pron_jpp[1]+pron_jpp[2]+tone_)
                ipas.append(pron_ipa[0]+pron_ipa[1]+pron_ipa[2]+tone)
            self.prons = jpps
            self.ipas = ipas
        def norm_and_to_jpp(self, norm_rule: List[Term], pron_rule: List[Term], tone_rule: Dict):
            split_prons = sorted([split_ipa(p) for p in self.ipas], key=lambda x:x[0][1]+x[0][2])
            jpps: List[str] = []
            ipas: List[str] = []
            for pron_, tone_ in split_prons:
                pron_ipa = pron_translate(rules=norm_rule, inp=pron_, to_jpp_or_ipa=None)
                pron_jpp = pron_translate(rules=pron_rule, inp=pron_ipa, to_jpp_or_ipa=True)
                checked_tone_mark = "舒聲" if pron_[2] not in ["p", "t", "k", "ʔ"] else "入聲"
                tone = tone_translate(rules=tone_rule[checked_tone_mark], tone_mark=tone_)
                jpps.append(pron_jpp[0]+pron_jpp[1]+pron_jpp[2]+tone)
                ipas.append(pron_ipa[0]+pron_ipa[1]+pron_ipa[2]+tone_)
            self.prons = jpps
            self.ipas = ipas
        def __str__(self) -> str:
            return (f"{self.prons}<{self.mean}>" if self.mean!="" else f"{self.prons}") + (f"/{'.'.join(self.ipas)}/" if self.ipas else "")
    multiprons: List[Pron]
    def __init__(self, index: int, chara: str, prons: List[str], mean: str, ipas: List[str]):
        self.index = index
        self.chara = chara
        self.multiprons = [Chara.Pron(prons, mean, ipas)]
    def __str__(self):
        return self.chara+" => " + ' | '.join([str(i) for i in self.multiprons])
    def append(self, pron: Pron) -> None:
        self.multiprons.append(pron)
    def rm_duplicate(self) -> None:
        assert len(self.multiprons)>=1
        if len(self.multiprons)==1: return
        multiprons = [Chara.Pron(m.prons.copy(), m.mean, m.ipas.copy()) for m in self.multiprons]
        for i in range(len(multiprons[:-1])):
            if len(multiprons[i].prons)==0: continue
            for j in range(len(multiprons[i+1:])):
                if len(multiprons[i+1+j].prons)==0: continue
                if multiprons[i]==multiprons[i+1+j]:
                    new_mean = ""
                    if multiprons[i].mean!="" and multiprons[i+1+j].mean!="":
                        if len(multiprons[i].prons)>1 or len(multiprons[i+1+j].prons)>1: continue #----#
                        if len(multiprons) > 2:
                            if multiprons[i].mean != multiprons[i+1+j].mean:
                                new_mean = multiprons[i].mean + "；" + multiprons[i+1+j].mean
                            else:
                                new_mean = multiprons[i].mean
                    else:
                        new_mean = multiprons[i].mean + multiprons[i+1+j].mean
                    new_prons_list = list(set(multiprons[i].prons+multiprons[i+1+j].prons))
                    new_ipas_list = list(set(multiprons[i].ipas+multiprons[i+1+j].ipas))
                    multiprons[i] = Chara.Pron(new_prons_list, new_mean, new_ipas_list)
                    multiprons[i+1+j].prons = []
                    logging.info(f"{self.index} 合併: {self.chara}: [{i}]{self.multiprons[i]}, [{i+1+j}]{self.multiprons[i+1+j]} => {multiprons[i]}")

        self.multiprons = [m for m in multiprons if len(m.prons)>0]
    def to_ipa(self, norm_rule: List[Term], pron_rule: List[Term], tone_rule: Dict) -> None:
        for i in self.multiprons:
            try:
                i.norm_and_to_ipa(norm_rule, pron_rule, tone_rule)
            except Exception as e:
                logging.error(f"{self.index} 未識別的音節 {self.chara}, {'/'.join([str(i) for i in self.multiprons])},【{e.args[0]}】")
                logging.debug(e)
                continue
    def to_jpp(self, norm_rule: List[Term], pron_rule: List[Term], tone_rule: Dict) -> None:
        for i in self.multiprons:
            try:
                i.norm_and_to_jpp(norm_rule, pron_rule, tone_rule)
            except Exception as e:
                logging.error(f"{self.index} 未識別的音節 {self.chara}, {'/'.join([str(i) for i in self.multiprons])},【{e.args[0]}】")
                logging.debug(e)
                continue


class Sheet:
    log: List[str] = []
    
    entry_list: List[Chara]
    chara_index_dict: Dict[str, int]
    is_set_ipas: bool
    is_set_pron: bool
    
    rule: Rule.Selected
    
    def __init__(self, df: pd.DataFrame, 
                locate: str, append_rule: List[Union[str,int]], 
                char_col : int,
                pron_cols: List[int],
                mean_cols: List[int],
                ipa_cols : List[int],
                pron_nd_cols: List[int],
                no_sim_to_trad: bool, keep_sim_to_trad: bool
                ):
        
        entry_list: List[Chara] = list()
        chara_index_dict: Dict[str, int] = dict()
        logging.info(f"總共 {len(df)} 行")
        self.logger("讀取字表", f"總共 {len(df)} 行")
        for sheet_index in range(len(df)):
            sheet_row = df.loc[sheet_index]
            # assert df.loc[sheet_index][use_col_index['pron'][0]] != "0.0", sheet_index
            # logging.debug("第 %d 行: %s", sheet_index, sheet_row)
            if not sheet_row[char_col] or isinstance(sheet_row[char_col], float): continue
            chara     = Sheet.__parse_chara(sheet_row[char_col])
            if chara in ["□"]: continue
            meaning   = Sheet.__parse_meaning([sheet_row[i] for i in mean_cols])
            _, ipas   = Sheet.__read_row_syllable([sheet_row[i].strip() for i in ipa_cols])
            syllables = Sheet.__parse_row_all_pron(sheet_index+2, chara, 
                            [sheet_row[i].strip() for i in pron_cols],
                            [sheet_row[i].strip() for i in pron_nd_cols])
            logging.debug(f"第 {sheet_index+2} 行: {(chara, syllables, meaning, ipas)}")
            self.logger("讀取字表", f"第 {sheet_index+2} 行: {(chara, syllables, meaning, ipas)}", "DEBUG")
            
            if len(syllables)==0 and len(ipas)==0: continue
            if chara not in chara_index_dict:
                chara_index_dict[chara] = len(entry_list)
                entry_list.append(Chara(sheet_index+2, chara, syllables, meaning, ipas))
            else:
                entry_list[chara_index_dict[chara]].append(Chara.Pron(syllables, meaning, ipas))
        logging.info(f"讀取 {len(entry_list)} 行")
        self.logger("讀取字表", f"讀取 {len(entry_list)} 行")
        self.entry_list = entry_list
        self.chara_index_dict = chara_index_dict
        self.rule, msg = RULE.select(locate, append_rule)
        logging.info(msg)
        self.logger("讀取轉寫規則: ", msg)
        
        is_set_ipa = len(ipa_cols)>0
        is_set_jpp = len(pron_cols)>0
        if is_set_ipa and not is_set_jpp: # 只有 ipa 沒有 jpp
            for i in self.entry_list:
                i.to_jpp(self.rule.i2i, self.rule.i2j, self.rule.tone_i2j)
        if is_set_jpp and not is_set_ipa: # 只有 jpp 沒有 ipa
            for i in self.entry_list:
                i.to_ipa(self.rule.j2j, self.rule.j2i, self.rule.tone_j2i)
        if not no_sim_to_trad:
            self.__sim_2_trad(keep_s2t=keep_sim_to_trad)
        logging.info("解析完成")
        self.logger("讀取字表", "完成")
    
    @staticmethod
    def __parse_chara(chara: str) -> str:
        return chara.strip()
    @staticmethod
    def __parse_meaning(meaning_: List[str], delimiter: str = "") -> str:
        meaning = delimiter.join(meaning_)
        if len(meaning)>0 and meaning[-1] in ["。", "；"]: meaning = meaning[:-1]
        return meaning.strip()
    @staticmethod
    def __parse_row_all_pron(rowidx:int, chara: str, pron_col_content: List[str], pron_col_nd_content: List[str]) -> List[str]:
        is_valid_main, pron_main = Sheet.__read_row_syllable(pron_col_content)
        is_valid_sub , pron_sub = Sheet.__read_row_syllable(pron_col_nd_content)
        if not is_valid_main or not is_valid_sub:
            logging.warning(f"{rowidx} 分隔符數目不匹配: {chara} {pron_main} {pron_sub}")
        # supposed to be the last column and there is no pron_sub column
        if len(pron_main) == 0:
            if len(pron_sub) != 0:
                logging.warning(f"{rowidx} 音節空缺: {chara} {pron_sub}")
        return pron_main + pron_sub
    @staticmethod
    def __read_row_syllable(elements: List[str]) -> Tuple[bool, List[str]]:
        if all([i=="" for i in elements]): return (True, [])
        elements = [i if isinstance(i, str) else str(i) for i in elements]
        elements[0] = elements[0] if elements[0]!="0.0" else "" # might costly
        elements_split = [i.split('/') for i in elements]
        seperator_count = [len(e)-1 for e in elements_split]
        seperator_count_filtered = list(filter(lambda x: x>0, seperator_count))
        if len(seperator_count_filtered)==0: return (True, ["".join(elements)])
        retrieve_loop_times = min(seperator_count_filtered)
        is_valid = retrieve_loop_times == max(seperator_count_filtered)
        elements_split_pad = [e+[e[-1]]*(retrieve_loop_times-len(e)+1) for e in elements_split]
        return (is_valid, ["".join([e[i] for e in elements_split_pad]) for i in range(retrieve_loop_times+1)])
    
    def logger(self, fn_name: str, msg: str, level: str="INFO"):
        if level == "DEBUG": return
        self.log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')} | {fn_name}: {level}] {msg}\n")
    def get_log(self) -> str:
        log = "\n".join(self.log)
        self.log = []
        return log
    
    def load_config(self, locale:str, append:List[Union[int, str]]) -> str:
        self.rule, msg = RULE.select(locale, append)
        return msg
    
    def __sim_2_trad(self, keep_s2t: bool) -> None:
        self.s2t_converter = opencc.OpenCC('s2t.json')
        s2t_keeped_char = {
            "干","后","系","历","板","表","丑","范","丰","刮","胡","回",
            "伙","姜","借","克","困","里","帘","面","蔑","千","秋","松",
            "咸","向","余","郁","御","愿","云","芸","沄","致","制","朱",
            "筑","准","辟","别","卜","斗","谷","划","几","据","卷",
            "了","累","朴","仆","曲","舍","胜","术","台","吁","佣","折",
            "征","症","采","吃","床","峰","杠","恒","栗","秘","凶","熏",
            "肴","占","苧","咨","粽","并","雇","广","么","霉","群","抬",
            "涂","托","涌","游","灶","皂","庄","么","岩","叶","坏","厘",
            "尸","个","冲","巩","碱","种","岳","于","网","万","糍",
            "夸","荐","杰","晒","痴","姹","麽","昵","蘖","唇","虱","宁",
            "膻","厂"
        }
        for entry in self.entry_list:
            chara = entry.chara
            chara_t = self.s2t_converter.convert(chara)
            if (chara_t!=chara) and chara in s2t_keeped_char:
                logging.debug(f"{entry.index} 簡轉繁未應用 {chara} -> {chara_t}")
                self.logger("簡轉繁", f"{entry.index} 簡轉繁未應用 {chara} -> {chara_t}", "DEBUG")
                pass
            if (chara_t!=chara) and chara not in s2t_keeped_char:
                if chara_t in self.chara_index_dict:
                    if not keep_s2t:
                        logging.warning(f"{entry.index} 簡轉繁重複 {chara} -> {chara_t}")
                        self.logger("簡轉繁", f"{entry.index} 簡轉繁重複 {chara} -> {chara_t}", "WARNING")
                        entry.status = -1
                        continue
                    else:
                        logging.debug(f"{entry.index} 簡轉繁保留 {chara} -> {chara_t}")
                        self.logger("簡轉繁", f"{entry.index} 簡轉繁保留 {chara} -> {chara_t}", "DEBUG")
                        pass
                else:
                    logging.warning(f"{entry.index} 簡轉繁 {chara} -> {chara_t}")
                    self.logger("簡轉繁", f"{entry.index} 簡轉繁 {chara} -> {chara_t}", "WARNING")
                    entry.chara = chara_t
                    entry.status = 1
                    self.chara_index_dict[chara_t] = self.chara_index_dict[chara]
                    self.chara_index_dict.pop(chara)
                    continue
    
    def query(self, chara: str) -> List[Chara.Pron]:
        if chara in self.chara_index_dict:
            return self.entry_list[self.chara_index_dict[chara]].multiprons
        else:
            return []
    
    def show_str_to_jpp(self, name: str) -> str:
        output_name_list: List[List[Chara.Pron]] = []
        for i in name:
            output_name_list.append(self.query(i))
        output_name_ = ""
        if all([len(j)==1 for j in output_name_list]) and all([len(j[0].prons)==1 for j in output_name_list]):
            output_name_ += output_name_list[0][0].prons[0].capitalize()
            output_name_ += output_name_list[1][0].prons[0]
            output_name_ += "".join([i[0].prons[0] for i in output_name_list[2:]]).capitalize()
        else:
            for i in output_name_list:
                if len(i) == 1:
                    output_name_ += i[0].prons[0] + "\n"
                else:
                    output_name_ += "{" + "/".join([str(j) for j in i]) + "}\n"
        return output_name_
    
    def output_sql_full(self, output_name: str) -> Tuple[int, int, str]:
        count_row, count_chara = 0, 0
        result = ""
        result += output_sql_header(output_name)
        for entry in self.entry_list:
            if entry.status == -1: continue
            for prons in entry.multiprons:
            # for prons in sorted(entry.multiprons, key=lambda x:x.prons[0]):
                ipas = "=".join(prons.ipas)
                ou_pron = "=".join(prons.prons)
                ou_ipa = "'" + ipas + "'" if "'" not in ipas else '"' + ipas + '"'
                ou_mean = "'" + prons.mean + "'" if "'" not in prons.mean else '"' + prons.mean + '"'
                
                result += f"{',' if count_row>0 else ''}\n({count_row+1},'{entry.chara}','{ou_pron}','','','',{ou_ipa},{ou_mean})"
                count_row += 1
            count_chara += 1
        result += ";"
        return (count_row, count_chara, result)

    
    
def output_sql_header(output_name):
    return \
"""CREATE TABLE `%s` (
  `id` int NOT NULL,
  `chara` tinytext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `initial` tinytext CHARACTER SET armscii8 COLLATE armscii8_bin NOT NULL,
  `nuclei` tinytext CHARACTER SET armscii8 COLLATE armscii8_bin NOT NULL,
  `coda` tinytext CHARACTER SET armscii8 COLLATE armscii8_bin NOT NULL,
  `tone` tinytext CHARACTER SET armscii8 COLLATE armscii8_bin NOT NULL,
  `ipa` tinytext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `note` text CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE `%s` ADD PRIMARY KEY(`id`);

INSERT INTO `%s` (`id`, `chara`, `initial`, `nuclei`, `coda`, `tone`, `ipa`, `note`) VALUES""".replace("%s", output_name)
