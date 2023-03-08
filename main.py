# encoding: utf-8
# python3
import pandas as pd
import opencc
import logging

from typing import Optional, Any, List, Tuple, Dict, Callable, Union
import argparse
from functools import reduce

from jpp_trasnlator import *

def print_ipa_process(syllable:str):
    syllables = []
    try:
        syllables = splite_jpp(syllable)
        logging.info(f"分割 {syllable} 成 {syllables}")
        ipa = get_ipa(locale_rule, syllables, locale_name)
    except TypeError as e:
        logging.error("含有不合法拼音或未兼容音素 ", syllables, e)
    else:
        logging.info(f"{syllable} -> {syllables} -> {ipa} -> {format_ipa(ipa)}")

class Chara:
    chara : str
    status: int = 0
    index : int = 0
    class Pron:
        prons: List[str]
        mean: str
        ipas: List[str]
        split_prons: List[List[str]]
        def __init__(self, prons: List[str], mean: str, ipas: List[str]):
            self.split_prons = sorted([splite_jpp(p) for p in prons], key=lambda x:x[1]+x[2])
            self.prons = list(map(lambda x: ''.join(x), self.split_prons))
            self.mean  = mean
            self.ipas  = ipas
        def __eq__(self, __o: object) -> bool:
            if not isinstance(__o, Chara.Pron): return False
            if any([p in __o.prons for p in self.prons]) and (self.mean!="" and self.mean==__o.mean): return True
            if all([p in __o.prons for p in self.prons]) or all([p in self.prons for p in __o.prons]): return True
            return False
        def toIpa(self, locale_rule: List[Union[int, str]], locale_name: str):
            self.ipas = [format_ipa(get_ipa(locale_rule, i, locale_name)) for i in self.split_prons]
        def __str__(self) -> str:
            return (f"{self.prons}<{self.mean}>" if self.mean!="" else f"{self.prons}") + (f"/{'.'.join(self.ipas)}/" if self.ipas else "")
    multiprons: List[Pron]
    def __init__(self, index: int, chara: str, prons: List[str], mean: str, ipas: List[str]):
        self.index = index
        self.chara = chara
        self.multiprons = [self.Pron(prons, mean, ipas)]
    def __str__(self):
        return self.chara+" => " + ' | '.join([str(i) for i in self.multiprons])
    def append(self, pron: Pron) -> None:
        self.multiprons.append(pron)
    def rm_duplicate(self) -> None:
        assert len(self.multiprons)>=1
        if len(self.multiprons)==1: return
        multiprons = [Chara.Pron(m.prons.copy(), m.mean, m.ipas.copy()) for m in self.multiprons] # costly, should be optimized
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
    def toIpa(self, locale_rule: List[Union[int, str]], locale_name: str) -> None:
        for i in self.multiprons:
            try:
                i.toIpa(locale_rule, locale_name)
            except Exception as e:
                logging.error(f"{self.index} 未識別的音節 {self.chara}, {'/'.join([str(i) for i in self.multiprons])},【{e.args[0]}】")
                logging.debug(e)
                continue
'''
chara: 重
multiprons: [
    (prons: [chung4], mean: v.), 
    (prons: [chung5, zhung6], mean: adj.), 
]
'''

def read_row_syllable(elements: List[str]) -> Tuple[bool, List[str]]:
    if all([i=="" for i in elements]): return (True, [])
    elements_split = [i.split('/') for i in elements]
    seperator_count = [len(e)-1 for e in elements_split]
    seperator_count_filtered = list(filter(lambda x: x>0, seperator_count))
    if len(seperator_count_filtered)==0: return (True, ["".join(elements)])
    retrieve_loop_times = min(seperator_count_filtered)
    is_valid = retrieve_loop_times == max(seperator_count_filtered)
    elements_split_pad = [e+[e[-1]]*(retrieve_loop_times-len(e)+1) for e in elements_split]
    return (is_valid, ["".join([e[i] for e in elements_split_pad]) for i in range(retrieve_loop_times+1)])

def read_sheet(df: pd.DataFrame, use_col_index: Dict[str, List[int]]) -> Tuple[List[Chara], Dict[str, int]]:
    entry_list: List[Chara] = list()
    chara_index_dict: Dict[str, int] = dict()
    logging.info("總共 %d 行", len(df))
    pron_col = use_col_index['pron']
    pron_nd_col = use_col_index['pron_nd']
    
    for sheet_index in range(len(df)):
        sheet_row = df.loc[sheet_index]
        # logging.debug("第 %d 行: %s", sheet_index, sheet_row)
        if not sheet_row[use_col_index['char'][0]] or isinstance(sheet_row[use_col_index['char'][0]], float): continue
        chara = sheet_row[use_col_index['char'][0]].strip()
        meaning = "".join([sheet_row[i] for i in use_col_index['mean']]) if len(use_col_index['mean'])>0 else ""
        ipas = ["".join([sheet_row[i] for i in use_col_index['ipa']])] if len(use_col_index['ipa'])>0 else []
        is_valid_main, pron_main = read_row_syllable([sheet_row[i].strip() for i in pron_col])#"".join([str(sheet_row[i]) for i in pron_col])
        is_valid_sub, pron_sub   = read_row_syllable([sheet_row[i].strip() for i in pron_nd_col])#"".join([str(sheet_row[i]) for i in pron_nd_col])
        if not is_valid_main or not is_valid_sub:
            logging.warning(f"{sheet_index+2} 分隔符數目不匹配: {chara} {pron_main} {pron_sub}")
        # supposed to be the last column and there is no pron_sub column
        logging.debug("第 %d 行: %s", sheet_index, (chara, pron_main, pron_sub, meaning, ipas))
        if len(pron_main) == 0:
            if len(pron_sub) != 0: logging.warning(f"{sheet_index+2} 音節空缺: {chara} {pron_sub} {meaning}")
            continue
        syllables: List[str] = pron_main + pron_sub
        if len(meaning)>0 and meaning[-1] in ["。", "；"]: meaning = meaning[:-1]
        if chara not in chara_index_dict:
            chara_index_dict[chara] = len(entry_list)
            entry_list.append(Chara(sheet_index+2, chara, syllables, meaning, ipas))
        else:
            entry_list[chara_index_dict[chara]].append(Chara.Pron(syllables, meaning, ipas))
    logging.info(f"讀取 {len(entry_list)} 行")
    return entry_list, chara_index_dict


def sim_2_trad(entry_list: List[Chara], chara_index_dict: Dict[str, int], keep_s2t: bool) -> Tuple[List[Chara], Dict[str, int]]:
    s2t_converter = opencc.OpenCC('s2t.json')
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
        "膻"
    }
    for entry in entry_list:
        chara = entry.chara
        chara_t = s2t_converter.convert(chara)
        if (chara_t!=chara) and chara in s2t_keeped_char:
            logging.debug("%d 簡轉繁未應用 %s -> %s", entry.index, chara, chara_t)
            pass
        if (chara_t!=chara) and chara not in s2t_keeped_char:
            if chara_t in chara_index_dict:
                if not keep_s2t:
                    logging.warning("%d 簡轉繁重複 %s -> %s", entry.index, chara, chara_t)
                    entry.status = -1
                    continue
                else:
                    logging.debug("%d 簡轉繁保留 %s -> %s", entry.index, chara, chara_t)
                    pass
            else:
                logging.warning("%d 簡轉繁 %s -> %s", entry.index, chara, chara_t)
                entry.chara = chara_t
                entry.status = 1
                chara_index_dict[chara_t] = chara_index_dict[chara]
                chara_index_dict.pop(chara)
                continue
    return entry_list, chara_index_dict


def retrieve_locale_name(entry_list: List[Chara], chara_index_dict: Dict[str, int], name: str) -> str:
    for i in name:
        if i in chara_index_dict: 
            logging.info(entry_list[chara_index_dict[i]])
        else:
            logging.warning(f"找不到 {i} 在 {name}")
    output_name_list = []
    for i in name:
        if i in chara_index_dict: 
            output_name_list.append(entry_list[chara_index_dict[i]].multiprons)
    if all([len(j)==1 for j in output_name_list]):
        output_name_ = "".join(output_name_list[0][0].split_prons[0][0:-1]).capitalize() + \
            "".join(output_name_list[1][0].split_prons[0][0:-1]) + \
            "".join(["".join(i[0].split_prons[0][0:-1]) for i in output_name_list[2:]]).capitalize()
    else:
        output_name_ = ""
    if not args_config.no_output:
        while True:
            if output_name_ == "":
                output_name_ = input("輸入輸出文件名: ")
            output_name_comfirm = input(f"確認輸出文件名為 Z{output_name_}，不是請輸入「n」: ")
            if output_name_comfirm != "n": break
            output_name_ = ""
    else:
        logging.info("輸出文件名為 Z"+output_name_)
    output_name_ = "Z" + output_name_
    return output_name_
    
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

def output_sql_full(entry_list:List[Chara], output_name: str, output_dir: str) -> Tuple[int, int]:
    output_full_path = os.path.join(output_dir, '%s.sql' % (output_name))
    count_row, count_chara = 0, 0
    with open(output_full_path, 'w', encoding='utf-8') as f:
        f.write(output_sql_header(output_name))
        for entry in entry_list:
            if entry.status == -1: continue
            for prons in entry.multiprons:
                ipas = "=".join(prons.ipas)
                ipa = "'" + ipas + "'" if "'" not in ipas else '"' + ipas + '"'
                mean = "'" + prons.mean + "'" if "'" not in prons.mean else '"' + prons.mean + '"'
                if len(prons.prons)>1:
                    f.write("%s\n(%d,'%s','%s','%s','%s','%s',%s,%s)" % ( "," if count_row>0 else "", 
                        count_row+1, entry.chara, "=".join(prons.prons), "", "", "",
                        ipa, mean))
                else:
                    f.write("%s\n(%d,'%s','%s','%s','%s','%s',%s,%s)" % ( "," if count_row>0 else "", 
                        count_row+1, entry.chara, prons.split_prons[0][0], prons.split_prons[0][1], prons.split_prons[0][2], prons.split_prons[0][3],
                        ipa, mean))
                count_row += 1
            count_chara += 1
        f.write(";")
    logging.info("輸出到: %s" % (output_full_path))
    return (count_row, count_chara)

trans_col_names_to_index = lambda names: names if isinstance(names, int) else (ord(names)-64 if isinstance(names, str) else [ord(name)-64 for name in names])

if __name__ == '__main__':
    os.system("cls")
    args_parser = argparse.ArgumentParser(description="從字表轉換到數據庫格式。    By EcisralHetha")
    args_parser.add_argument('-l', '--locale-name', type=str, help='地名，需要包括小地名在內的全名')
    args_parser.add_argument('-i', '--file-path', type=str, required=True,  help='輸入字表路徑')
    args_parser.add_argument('-o', '--output-dir', type=str, default="./output", help='輸出目錄')
    args_parser.add_argument('-n', '--sheet-name', type=str, help='表格所在的表名', default='主表')
    #args_parser.add_argument('-v', '--version', action='version', version='v0.5/211017')
    args_parser.add_argument('--no-output', action='store_true', help='不輸出 SQL 文件')
    args_parser.add_argument('-c', '--char', type=str, help='字頭所在列', required=True)
    args_parser.add_argument('-p', '--pron', type=str, help='拼音所在列', required=True)
    args_parser.add_argument('-P', '--pron_nd', type=str, help='次音所在列')
    args_parser.add_argument('-m', '--mean', type=str, help='釋義所在列')
    args_parser.add_argument('-I', '--ipa', type=str, help='IPA 所在列')
    args_parser.add_argument('--keep-s2t', action='store_true', help='保留簡體字')
    args_parser.add_argument('--debug', action='store_true', help='顯示詳細資訊')
    args_parser.add_argument('-j', '--jpp2ipa', type=str, help='將攜帶的粵拼參數轉為 IPA')
    args_config = args_parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args_config.debug else logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
    logging.debug(args_config)
    
    output_dir  = args_config.output_dir
    input_path  = args_config.file_path
    if not os.path.exists(output_dir): os.mkdir(output_dir)
    if not os.path.exists(input_path):
        logging.error("輸入文件不存在")
        exit(1)
    
    locale_name :str = args_config.locale_name if args_config.locale_name else os.path.basename(input_path).split(" ")[0] 
    sheet_name  :str = args_config.sheet_name#"Sheet1"
    
    char_col    :str = args_config.char
    pron_col    :str = args_config.pron
    pron_nd_col :str = args_config.pron_nd if args_config.pron_nd else ""
    mean_col    :str = args_config.mean
    ipa_col     :str = args_config.ipa
    
    char_col_index    = [ord(char_col) - 65]
    pron_col_index    = [ord(i) - 65 for i in pron_col]
    pron_nd_col_index = [ord(i) - 65 for i in pron_nd_col]
    mean_col_index    = [ord(i) - 65 for i in mean_col] if args_config.mean else []
    ipa_col_index     = [ord(i) - 65 for i in ipa_col]  if args_config.ipa  else []
    use_col_index: Dict[str, List[int]] = {
        "char":char_col_index, "mean":mean_col_index, "ipa":ipa_col_index, "pron":pron_col_index, "pron_nd":pron_nd_col_index}
    logging.debug("use_col_index: %s" % use_col_index)
    
    locale_rule = [0, 1, locale_name]
    
    try:
        if not args_config.jpp2ipa:
            logging.info("0____讀取文件____")
            data_file = pd.read_excel(input_path, sheet_name=sheet_name, keep_default_na=False, dtype=str)
            
            logging.info("1____讀取字表____")
            entry_list, chara_index_dict = read_sheet(data_file, use_col_index)
            
            logging.info("2___合併重複音節____")
            for entry in entry_list: entry.rm_duplicate()
            
            logging.info("3___簡轉繁____")
            entry_list, chara_index_dict = sim_2_trad(entry_list, chara_index_dict, args_config.keep_s2t)
            
            if len(ipa_col_index)>0:
                logging.info("4____自带IPA，不需轉換____")
            else:
                logging.info("4____取得IPA____")
                for entry in entry_list: entry.toIpa(locale_rule, locale_name)
                
            logging.info("5____輸出當地名粵拼____")
            output_name = retrieve_locale_name(entry_list, chara_index_dict, locale_name)
            
            if not args_config.no_output:
                logging.info("6____輸出文件____")
                count_row, count_chara = output_sql_full(entry_list, output_name, output_dir)
                logging.info(f"共 {len(data_file)} 行, 有效 {count_row} 行, {count_chara} 字")
            logging.info("7____完成____")
        else:
            print_ipa_process(args_config.jpp2ipa)
    except KeyboardInterrupt as e:
        print()
        logging.error("用戶中斷")
    