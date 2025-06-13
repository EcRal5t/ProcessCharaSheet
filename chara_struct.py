# encoding: utf-8
# python3
# filename: chara_struct.py

import logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s | %(funcName)s: %(levelname)s] %(message)s')
from typing import Optional, Any, List, Tuple, Dict, Callable, Union, Set

import pandas as pd
import opencc

from chara_trasnlator import ToneDict, Term, Rule, RULE, pron_translate, tone_translate, split_jpp, split_ipa

class Chara:
    """
    代表一個漢字（字頭）及其所有相關的讀音和釋義。
    
    Attributes:
        chara (str): 漢字本身，例如 '東'。
        status (int): 字頭的狀態標記。0=正常, 1=由簡轉繁, -1=簡轉繁時與現有字碰撞。
        index (int): 該字在原始表格中的行號。
        multiprons (List[Pron]): 一個列表，包含该字的所有讀音（Pron物件）。
    """
    chara : str
    status: int = 0
    index : int = 0
    
    class Pron:
        """
        代表一個漢字的單一讀音（或一組異讀）。
        
        Attributes:
            prons (List[str]): 此讀音對應的粵拼列表。
            mean (str): 此讀音的釋義，例如 "文讀" 或 "白讀"。
            ipas (List[str]): 對應的國際音標 (IPA) 列表。
        """
        prons: List[str]
        mean: str
        ipas: List[str]
        
        def __init__(self, prons: List[str], mean: str, ipas: List[str]):
            self.prons = prons
            self.mean  = mean
            self.ipas  = ipas
            
        def __eq__(self, __o: object) -> bool:
            """
            判斷兩個 Pron 物件是否相等，用於去重。
            如果讀音有交集且釋義相同，或兩者讀音列表完全一致，則視為相等。
            """
            if not isinstance(__o, Chara.Pron): return False
            # 釋義相同且有任一讀音相同
            if any([p in __o.prons for p in self.prons]) and (self.mean!="" and self.mean==__o.mean): return True
            # 兩個讀音列表互為子集（即完全相同）
            if all([p in __o.prons for p in self.prons]) or all([p in self.prons for p in __o.prons]): return True
            return False
        
        def norm_and_to_ipa(self, norm_rule: List[Term], pron_rule: List[Term], mark_rule: ToneDict, tone_rule: ToneDict):
            """
            將自身的粵拼（jpp）讀音正則化並轉換為國際音標（IPA）。
            
            Args:
                norm_rule (List[Term]): j2j 粵拼到粵拼的正則化規則。
                pron_rule (List[Term]): j2i 粵拼到音標的轉換規則。
                mark_rule (ToneDict): t_j2j 粵拼聲調的標記規則。
                tone_rule (ToneDict): t_j2i 粵拼聲調到音標聲調的轉換規則。
            """
            # 先按韻母+韻尾排序，保證處理順序穩定
            split_prons = sorted([split_jpp(p) for p in self.prons], key=lambda x:x[0][1]+x[0][2])
            jpps: List[str] = []
            ipas: List[str] = []
            for pron_, tone_ in split_prons:
                # 應用 j2j 規則對粵拼進行正則化
                pron_jpp = pron_translate(rules=norm_rule, inp=pron_,    to_jpp_or_ipa=None)
                # 應用 j2i 規則將正則化後的粵拼轉為 IPA
                pron_ipa = pron_translate(rules=pron_rule, inp=pron_jpp, to_jpp_or_ipa=False)
                # 轉換聲調
                checked_tone_mark = "舒聲" if pron_[2] not in ["p", "t", "k", "h"] else "入聲"
                tone_jpp = tone_translate(rules=mark_rule.get(checked_tone_mark, {}), tone_mark=tone_, skippable=True)
                tone_ipa = tone_translate(rules=tone_rule.get(checked_tone_mark, {}), tone_mark=tone_jpp)
                
                jpps.append(pron_jpp[0]+pron_jpp[1]+pron_jpp[2]+tone_jpp)
                ipas.append(pron_ipa[0]+pron_ipa[1]+pron_ipa[2]+tone_ipa)
            self.prons = jpps
            self.ipas = ipas
            
        def norm_and_to_jpp(self, norm_rule: List[Term], pron_rule: List[Term], tone_rule: ToneDict):
            """
            將自身的國際音標（IPA）讀音正則化並轉換為粵拼（jpp）。
            
            Args:
                norm_rule (List[Term]): i2i 音標到音標的正則化規則。
                pron_rule (List[Term]): i2j 音標到粵拼的轉換規則。
                tone_rule (ToneDict): t_i2j 音標聲調到粵拼聲調的轉換規則。
            """
            split_prons = sorted([split_ipa(p) for p in self.ipas], key=lambda x:x[0][1]+x[0][2])
            jpps: List[str] = []
            ipas: List[str] = []
            for pron_, tone_ in split_prons:
                pron_ipa = pron_translate(rules=norm_rule, inp=pron_,    to_jpp_or_ipa=None)
                pron_jpp = pron_translate(rules=pron_rule, inp=pron_ipa, to_jpp_or_ipa=True)
                checked_tone_mark = "舒聲" if pron_[2] not in ["p", "t", "k", "ʔ"] else "入聲"
                tone = tone_translate(rules=tone_rule.get(checked_tone_mark, {}), tone_mark=tone_)
                jpps.append(pron_jpp[0]+pron_jpp[1]+pron_jpp[2]+tone)
                ipas.append(pron_ipa[0]+pron_ipa[1]+pron_ipa[2]+tone_)
            self.prons = jpps
            self.ipas = ipas
            
        def __str__(self) -> str:
            """返回一個字符串表示，格式如：['jyut6']<釋義>/jyt6/"""
            return (f"{self.prons}<{self.mean}>" if self.mean!="" else f"{self.prons}") + (f"/{'.'.join(self.ipas)}/" if self.ipas else "")
        
    multiprons: List[Pron]
    def __init__(self, index: int, chara: str, prons: List[str], mean: str, ipas: List[str]):
        self.index = index
        self.chara = chara
        self.multiprons = [Chara.Pron(prons, mean, ipas)]
        
    def __str__(self):
        return self.chara+" => " + ' | '.join([str(i) for i in self.multiprons])
    
    def append(self, pron: Pron) -> None:
        """為當前字頭添加一個新的讀音。"""
        self.multiprons.append(pron)
        
    def rm_duplicate(self) -> None:
        """移除並合併當前字頭下的重複讀音。"""
        assert len(self.multiprons)>=1
        if len(self.multiprons)==1: return
        
        # 創建一個副本進行操作，避免在遍歷時修改列表
        multiprons = [Chara.Pron(m.prons.copy(), m.mean, m.ipas.copy()) for m in self.multiprons]
        for i in range(len(multiprons[:-1])):
            if len(multiprons[i].prons)==0: continue # 跳過已被合併的項
            for j in range(len(multiprons[i+1:])):
                if len(multiprons[i+1+j].prons)==0: continue # 跳過已被合併的項
                
                if multiprons[i]==multiprons[i+1+j]:
                    # 合併釋義
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
                    
                    # 合併讀音和音標列表，並去重
                    new_prons_list = list(set(multiprons[i].prons+multiprons[i+1+j].prons))
                    new_ipas_list = list(set(multiprons[i].ipas+multiprons[i+1+j].ipas))
                    
                    # 更新當前項，並清空被合併的項
                    multiprons[i] = Chara.Pron(new_prons_list, new_mean, new_ipas_list)
                    multiprons[i+1+j].prons = []
                    logging.info(f"{self.index} 合併: {self.chara}: [{i}]{self.multiprons[i]}, [{i+1+j}]{self.multiprons[i+1+j]} => {multiprons[i]}")

        # 移除所有被清空的項
        self.multiprons = [m for m in multiprons if len(m.prons)>0]
        
    def rm_redundant_mean(self) -> None:
        """如果一個字只有單一讀音，則其釋義通常是多餘的，將其移除。"""
        if len(self.multiprons) == 1:
            for i in range(len(self.multiprons)):
                logging.debug(f"{self.index} 刪除: {self.chara}: [{i}]{self.multiprons[i]}")
                self.multiprons[i].mean = ""
                
    def to_ipa(self, norm_rule: List[Term], pron_rule: List[Term], mark_rule: ToneDict, tone_rule: ToneDict) -> None:
        """對該字的所有讀音執行粵拼到音標的轉換。"""
        for i in self.multiprons:
            try:
                i.norm_and_to_ipa(norm_rule, pron_rule, mark_rule, tone_rule)
            except Exception as e:
                logging.error(f"{self.index} 未識別的音節 {self.chara}, {'/'.join([str(i) for i in self.multiprons])},【{e.args[0]}】")
                logging.debug(e)
                continue
            
    def to_jpp(self, norm_rule: List[Term], pron_rule: List[Term], tone_rule: ToneDict) -> None:
        """對該字的所有讀音執行音標到粵拼的轉換。"""
        for i in self.multiprons:
            try:
                i.norm_and_to_jpp(norm_rule, pron_rule, tone_rule)
            except Exception as e:
                logging.error(f"{self.index} 未識別的音節 {self.chara}, {'/'.join([str(i) for i in self.multiprons])},【{e.args[0]}】")
                logging.debug(e)
                continue


class Sheet:
    """
    代表整個字表文件，負責讀取、處理和輸出。
    """
    log: List[str] = []
    
    entry_list: List[Chara]
    chara_index_dict: Dict[str, int]
    is_set_ipas: bool
    is_set_pron: bool
    
    rule: Rule.Selected
    
    def __init__(self, df: pd.DataFrame, 
                locate: str, append_rule: List[Union[str,int]], 
                char_col : int,          # 字頭在 excel 表格中所在列
                pron_cols: List[int],    # 讀音在 excel 表格中所在（幾）列
                mean_cols: List[int],    # 釋義在 excel 表格中所在（幾）列
                ipa_cols : List[int],    # 音標在 excel 表格中所在（幾）列
                pron_nd_cols: List[int], # 另讀；舊格式，已棄用
                no_sim_to_trad: bool, keep_sim_to_trad: bool, cc_mean: bool, remove_redundant_mean: bool
                ):
        """
        Sheet的建構函數，執行主要的處理流程。

        Args:
            df (pd.DataFrame): 從Excel文件讀取的數據。
            locate (str): 方言地點，用於選擇轉換規則。
            append_rule (List[Union[str,int]]): 附加的通用規則。
            *various _cols (int or List[int]): 指定字頭、讀音、釋義等在DataFrame中的列索引。
            *various bool flags*: 控制是否進行簡轉繁、是否保留釋義等操作。
        """
        
        entry_list: List[Chara] = list()
        chara_index_dict: Dict[str, int] = dict()
        logging.info(f"總共 {len(df)} 行")
        
        # --- 1. 讀取 DataFrame 並解析成 Chara 物件 ---
        for sheet_index in range(len(df)):
            sheet_row  = df.loc[sheet_index]
            assert isinstance(sheet_row, pd.Series)
            # assert df.loc[sheet_index][use_col_index['pron'][0]] != "0.0", sheet_index
            # logging.debug("第 %d 行: %s", sheet_index, sheet_row)
            if not sheet_row.iloc[char_col] or isinstance(sheet_row.iloc[char_col], float): continue
            
            # 解析每行的字頭、釋義、音標和粵拼
            chara     = Sheet.__parse_chara(sheet_index, sheet_row.iloc[char_col])
            if chara in ["□"]: continue
            meaning   = Sheet.__parse_meaning([sheet_row.iloc[i] for i in mean_cols])
            _, ipas   = Sheet.read_row_syllable([sheet_row.iloc[i].strip() for i in ipa_cols])
            syllables = Sheet.__parse_row_all_pron(sheet_index+2, chara, 
                            [sheet_row.iloc[i].strip() for i in pron_cols],
                            [sheet_row.iloc[i].strip() for i in pron_nd_cols])
            logging.debug(f"第 {sheet_index+1} 行: {(chara, syllables, meaning, ipas)}")
            
            if len(syllables)==0 and len(ipas)==0: continue # 如果沒有任何讀音信息，則跳過
            
            # 如果是新字頭，創建 Chara 物件；如果是已有字頭，則添加新讀音
            if chara not in chara_index_dict:
                chara_index_dict[chara] = len(entry_list)
                entry_list.append(Chara(sheet_index+1, chara, syllables, meaning, ipas))
            else:
                entry_list[chara_index_dict[chara]].append(Chara.Pron(syllables, meaning, ipas))
        logging.info(f"讀取 {len(entry_list)} 行")
        
        is_set_ipa = len(ipa_cols)>0
        is_set_jpp = len(pron_cols)>0
        
        # --- 2. 數據清理與預處理 ---
        if is_set_jpp:
            for entry in entry_list: entry.rm_duplicate() # 移除重複讀音
        
        self.entry_list = entry_list
        self.chara_index_dict = chara_index_dict
        self.rule, msg = RULE.select(locate, append_rule) # 根據地點選擇轉換規則
        logging.info("讀取轉寫規則: " + msg)
        
        # --- 3. 粵拼/音標互轉 ---
        # 如果只有IPA，沒有粵拼，則生成粵拼
        if is_set_ipa and not is_set_jpp: # 只有 ipa 沒有 jpp
            logging.info("正在將音標轉換至粵拼")
            for i in self.entry_list:
                i.to_jpp(self.rule.i2i, self.rule.i2j, self.rule.tone_i2j)
        # 如果只有粵拼，沒有IPA，則生成IPA
        if is_set_jpp and not is_set_ipa: # 只有 jpp 沒有 ipa
            logging.info("正在將粵拼轉換至音標")
            for i in self.entry_list:
                i.to_ipa(self.rule.j2j, self.rule.j2i, self.rule.tone_j2j, self.rule.tone_j2i)
        
        # 如果原先沒有粵拼，生成後再進行一次去重
        if not is_set_jpp:
            for entry in entry_list: entry.rm_duplicate()
        
        # --- 4. 簡繁轉換和其他清理 ---
        if not no_sim_to_trad:
            self.__sim_2_trad(keep_chara_s2t=keep_sim_to_trad, cc_mean=cc_mean)
        if remove_redundant_mean:
            for i in self.entry_list:
                i.rm_redundant_mean()
    
    @staticmethod
    def __parse_chara(rowidx:int, chara: str) -> str:
        """解析字頭，如果一個單元格有多個字，則發出警告並取第一個。"""
        chara_stripped = chara.strip()
        if len(chara_stripped)>1:
            logging.warning(f"{rowidx} 似乎含有多個字: {chara}")
            return chara_stripped[0]
        return chara_stripped
    
    @staticmethod
    def __parse_meaning(meaning_: List[str], delimiter: str = "｜") -> str:
        """合併多個釋義列的內容。"""
        meaning = delimiter.join(filter(lambda x: x, meaning_))
        if len(meaning)>0 and meaning[-1] in ["。", "；"]: meaning = meaning[:-1]
        return meaning.strip()
    
    @staticmethod
    def __parse_row_all_pron(rowidx:int, chara: str, pron_col_content: List[str], pron_col_nd_content: List[str]) -> List[str]:
        """合併主讀音列和另讀音列的內容。"""
        is_valid_main, pron_main = Sheet.read_row_syllable(pron_col_content)
        is_valid_sub , pron_sub = Sheet.read_row_syllable(pron_col_nd_content)
        if not is_valid_main or not is_valid_sub:
            logging.warning(f"{rowidx} 分隔符數目不匹配: {chara} {pron_main} {pron_sub}")
        # supposed to be the last column and there is no pron_sub column
        if len(pron_main) == 0:
            if len(pron_sub) != 0:
                logging.warning(f"{rowidx} 音節空缺: {chara} {pron_sub}")
        return pron_main + pron_sub
    
    @staticmethod
    def read_row_syllable(elements: List[str]) -> Tuple[bool, List[str]]:
        """
        解析一行中表示讀音的單元格。
        能處理多列組合（如聲母、韻母、聲調分列）和單元格內用'/'分隔的多個讀音。
        例如，['h/j', 'oeng', '1'] -> ['hoeng1', 'joeng1']
        """
        if all([i=="" for i in elements]): return (True, [])
        elements = [i if isinstance(i, str) else str(i) for i in elements]
        elements[0] = elements[0] if elements[0]!="0.0" else ""
        elements_split = [i.split('/') for i in elements]
        seperator_count = [len(e)-1 for e in elements_split]
        seperator_count_filtered = list(filter(lambda x: x>0, seperator_count))
        if len(seperator_count_filtered)==0: return (True, ["".join(elements)])
        retrieve_loop_times = min(seperator_count_filtered)
        is_valid = retrieve_loop_times == max(seperator_count_filtered)
        elements_split_pad = [e+[e[-1]]*(retrieve_loop_times-len(e)+1) for e in elements_split]
        return (is_valid, ["".join([e[i] for e in elements_split_pad]) for i in range(retrieve_loop_times+1)])
    
    def get_log(self) -> str:
        log = "\n".join(self.log)
        self.log = []
        return log
    
    def load_config(self, locale:str, append:List[Union[int, str]]) -> str:
        self.rule, msg = RULE.select(locale, append)
        return msg
    
    s2t_converter: opencc.OpenCC
    s2t_keeped_char: Set[str]
    def __sim_2_trad(self, keep_chara_s2t: bool, cc_mean: bool) -> None:
        """
        執行簡體到繁體的轉換。
        使用 opencc 工具，並維護一個不進行轉換的例外列表 (s2t_keeped_char)，
        以處理“一簡對多繁”或在簡繁中均常用但意義不同的字。
        """
        self.s2t_converter = opencc.OpenCC('s2t.json')
        self.s2t_keeped_char = {
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
            # 如果是例外字，不轉換
            if (chara_t!=chara) and chara in self.s2t_keeped_char:
                logging.debug(f"{entry.index} 簡轉繁未應用 {chara} -> {chara_t}")
                pass
            if (chara_t!=chara) and chara not in self.s2t_keeped_char:
                # 如果轉換後的繁體字已存在於字典中，則產生碰撞
                if chara_t in self.chara_index_dict:
                    if not keep_chara_s2t:
                        logging.warning(f"{entry.index} 簡轉繁碰撞 {chara} -> {chara_t}")
                        entry.status = -1
                        continue
                    else:
                        logging.debug(f"{entry.index} 簡轉繁保留 {chara} -> {chara_t}")
                        pass
                else:
                    # logging.warning(f"{entry.index} 簡轉繁 {chara} -> {chara_t}")
                    entry.chara = chara_t
                    entry.status = 1 # 標記為已轉換
                    # 更新索引字典
                    self.chara_index_dict[chara_t] = self.chara_index_dict[chara]
                    self.chara_index_dict.pop(chara)
                    continue
        # 根據選項，對釋義也進行簡轉繁
        if cc_mean:
            for entry in self.entry_list:
                for multipron in entry.multiprons:
                    multipron.mean = self.s2t_converter.convert(multipron.mean)
        
    
    def query(self, charas: str) -> List[List[Chara.Pron]]:
        """查詢一個字符串中每個字的讀音。"""
        result: List[List[Chara.Pron]] = []
        for chara in charas:
            if chara in self.chara_index_dict:
                result.append(self.entry_list[self.chara_index_dict[chara]].multiprons)                
            else:
                result.append([])
        return result
    
    def show_str_to_jpp(self, name: str) -> str:
        """將一個詞語轉換成格式化的粵拼字符串。"""
        output_name_list = self.query(name)
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
    
    def output_sql_full(self, output_name: str, sort_pron: bool = False) -> Tuple[int, int, str]:
        """
        將處理完成的所有數據生成為 SQL INSERT 語句。

        Args:
            output_name (str): 要生成的SQL數據表名稱。
            sort_pron (bool, optional): 是否按字母表順序排序讀音

        Returns:
            Tuple[int, int, str]: (總行數, 總字數, SQL語句字符串)。
        """
        count_row, count_chara = 0, 0
        result = ""
        result += output_sql_header(output_name) # 添加 CREATE TABLE 頭部
        for entry in self.entry_list:
            if entry.status == -1: continue # 跳過碰撞的字
            multiprons = entry.multiprons if not sort_pron else sorted(entry.multiprons, key=lambda x:x.prons[0])
            for prons in multiprons:
                # 格式化輸出
                ipas = "=".join(prons.ipas)
                pron = "=".join(prons.prons)
                out_pron = "'" + pron + "'" if "'" not in pron else '"' + pron + '"'
                out_ipa = "'" + ipas + "'" if "'" not in ipas else '"' + ipas + '"'
                out_mean = "'" + prons.mean + "'" if "'" not in prons.mean else '"' + prons.mean + '"'
                
                result += f"{',' if count_row>0 else ''}\n({count_row+1},'{entry.chara}',{out_pron},'','','',{out_ipa},{out_mean})"
                count_row += 1
            count_chara += 1
        result += ";"
        return (count_row, count_chara, result)

def get_col_index(colname: str) -> int:
    """將 Excel 風格的列名（如 'A', 'B', 'AA'）或數字轉換為 0-based 的列索引。"""
    if colname.isdigit():
        return int(colname)
    elif len(colname)>1:
        r = [get_col_index(i) for i in colname.replace(" ", "").replace(",", "") if i != ""]
        logging.warning(f"多個欄位名: {colname}，取第一個: {r[0]}")
        return r[0]
    elif colname.isupper():
        return ord(colname)-65 # 'A' -> 0
    else:
        return ord(colname)-97 # 'a' -> 0
    
def output_sql_header(output_name):
    """生成 SQL 數據庫的 CREATE TABLE 和 INSERT INTO 語句頭部。"""
    return \
"""CREATE TABLE IF NOT EXISTS `%s` (
  `id` int NOT NULL,
  `chara` tinytext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `initial` tinytext CHARACTER SET armscii8 COLLATE armscii8_bin NOT NULL,
  `nuclei` tinytext CHARACTER SET armscii8 COLLATE armscii8_bin NOT NULL,
  `coda` tinytext CHARACTER SET armscii8 COLLATE armscii8_bin NOT NULL,
  `tone` tinytext CHARACTER SET armscii8 COLLATE armscii8_bin NOT NULL,
  `ipa` tinytext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `note` text CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
TRUNCATE TABLE `%s`;

INSERT INTO `%s` (`id`, `chara`, `initial`, `nuclei`, `coda`, `tone`, `ipa`, `note`) VALUES""".replace("%s", output_name)
