import pandas as pd
import numpy as np
import opencc

from typing import Optional, Union, Any, Set, List, Tuple
import argparse
from jpp_trasnlator import *

def print_ipa_process(syllable, locale_rules, locale_name):
    syllable_splited = []
    try:
        syllable_splited = splite_jpp(syllable)
        ipa = get_ipa(locale_rules, syllable_splited, locale_name)
    except TypeError as e:
        print("含有不合法拼音或未兼容音素 ", syllable_splited, e)
    else:
        print(f"{syllable} -> {syllable_splited} -> {ipa} -> {format_ipa(ipa)}")

def jpp2ipa_whole_sheet_and_output(input_path, locale_name, locale_rules, output_name, args_config):
    df = pd.read_excel(input_path, sheet_name=["主表"])[0]
    entry_set = set()
    s2t_converter = opencc.OpenCC('s2t.json')
    s2t_keeped_char = {
        "干","后","系","历","板","表","丑","范","丰","刮","胡","回",
        "伙","姜","借","克","困","里","帘","面","蔑","千","秋","松",
        "咸","向","余","郁","御","愿","云","芸","沄","致","制","朱",
        "筑","准","辟","别","卜","党","斗","谷","划","几","据","卷",
        "了","累","朴","仆","曲","舍","胜","术","台","吁","佣","折",
        "征","症","采","吃","床","峰","杠","恒","栗","秘","凶","熏",
        "肴","占","苧","咨","粽","并","雇","广","么","霉","群","抬",
        "涂","托","涌","游","灶","皂","庄","么","岩","叶","坏","厘",
        "尸","个","冲","巩","碱","凄","种","岳","于","网","万","糍",
        "夸","荐","杰","晒","痴","姹","麽","昵","蘖","唇","虱","宁",
    }
    sheet_index = 0
    characters = set()
    
    CHAR_COL = 0
    PRON_COL = [1,2,3]
    PRON_ND_COL = [5,6,7]
    IPA_COL = None
    
    with open(OUTPUT_DIR+'%s.sql' % (output_name), 'w', encoding='utf-8') as f:
        f.write(output_sql_header(output_name))
        index = 1
        for sheet_index in range(len(df)):
            sheet_row = df.loc[sheet_index]
            if not sheet_row[CHAR_COL] or isinstance(sheet_row[CHAR_COL], float): continue
            character = sheet_row[CHAR_COL].strip()
            character_t = s2t_converter.convert(character)
            if (character_t!=character) and character not in s2t_keeped_char:
                if character_t in characters:
                    print(sheet_index, "簡轉繁重複", character, "->", character_t)
                    continue
                else:
                    print(sheet_index, "簡轉繁", character, "->", character_t)
                    continue
                    character = character_t
            # if not sheet_row[CHAR_COL] or isinstance(sheet_row[CHAR_COL], float):
            #     if np.isnan(sheet_row[CHAR_COL]): continue
            #     print(sheet_index, "數字單元格", character, sheet_row[CHAR_COL])
            #     continue
            
            syllables = [
                sheet_row[PRON_COL[0]]+sheet_row[PRON_COL[1]]+sheet_row[PRON_COL[2]], 
                sheet_row[PRON_ND_COL[0]]+sheet_row[PRON_ND_COL[1]]+sheet_row[PRON_ND_COL[2]]
            ] #[sheet_row[CHARA_PRON]] #[i.strip() for i in sheet_row[1].split("=")]
            
            for k in sheet_row[(3 if not args_config.ipa else 4):]:
                if k and not isinstance(k, float) and k not in syllables:
                    syllables.append(k)
                    
            if not isinstance(syllables, list) or len(syllables)==0:
                print(sheet_index, "音節為空", character)
                continue
            
            if args_config.ipa:
                ipa = "" if args_config.noipa or len(sheet_row)<3 or (not isinstance(sheet_row[2], str)) else sheet_row[2].strip()
                meaning = "" if len(sheet_row)<4 or (not isinstance(sheet_row[3], str)) else sheet_row[3].strip()
            else:
                meaning = "" if len(sheet_row)<3 or (not isinstance(sheet_row[2], str)) else sheet_row[2].strip()
            meaning = meaning.replace("\sheet_index", " ")
            entry_exist_marker = []
            for i in syllables: 
                entry_info_merge = "%s-%s" % (character, i) # "%s-%s-%s" % (character, i, meaning)
                entry_exist_marker.append(entry_info_merge in entry_set)
                entry_set.add(entry_info_merge)
            if all(entry_exist_marker):
                print(sheet_index, "重複字頭: ", character, syllables)
                continue
            
            syllables_splited = [splite_jpp(i) for i in syllables]
            
            if not args_config.noipa and not args_config.ipa:
                try:
                    ipas = [format_ipa(get_ipa(locale_rules, i, locale_name)) for i in syllables_splited]
                    ipa = "=".join(ipas)
                except Exception as e:
                    print(sheet_index, character, syllables_splited, e)
                    continue
            
            characters.add(character)
            
            ipa = "'" + ipa + "'" if "'" not in ipa else '"' + ipa + '"'
            syllable_splited = syllables_splited[0]
            meaning = "'" + meaning + "'" if "'" not in meaning else '"' + meaning + '"'
            
            if len(syllables_splited)>1:
                f.write("%s\sheet_index(%d,'%s','%s','%s','%s','%s',%s,%s)" % ( "," if sheet_index>0 else "", 
                    index, character, "=".join(syllables), "", "", "",
                    ipa, meaning))
            else:
                f.write("%s\sheet_index(%d,'%s','%s','%s','%s','%s',%s,%s)" % ( "," if sheet_index>0 else "", 
                    index, character, syllable_splited[0], syllable_splited[1], syllable_splited[2], syllable_splited[3],
                    ipa, meaning))
            index += 1
        f.write(";")
    print(f"共 {sheet_index+1} 行, 有效 {index-1} 行")

def output_sql_header(output_name):
    return """CREATE TABLE `%s` (
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

if __name__ == '__main__':
    args_parser = argparse.ArgumentParser(description="使用演變表一鍵轉換出字表    By EcisralHetha")
    #args_parser.add_argument('地名', type=str, help='地名，需要包括小地名在內的全名')
    #args_parser.add_argument('-i', '--輸入路徑', type=str, default='./泛粵字表 21.xlsx', help='泛粵表本體的路徑，默認 = "./泛粵字表 21.xlsx"')
    args_parser.add_argument('--ipa', help='自帶IPA', action='store_true')
    args_parser.add_argument('--noipa', help='不轉換IPA', action='store_true')
    args_parser.add_argument('--equ', help='使用多音等号', action='store_true')
    #args_parser.add_argument('-v', '--version', action='version', version='v0.5/211017')
    args_config = args_parser.parse_args()
    #print(args_config)
    
    OUTPUT_DIR = "D:/C_KheuyMyenDong/Desktop/Jyutdict/SQL_new/"
    input_path = 'D:/C_KheuyMyenDong/Desktop/Jyutdict/未處理 原字表/端州.xlsx'
    output_name = "ZSiuhing_"
    locale_name = "端州"#input_path.split('/')[-1].split(" ")[0]
    locale_rules = [0, 1, locale_name]
    
    jpp2ipa_whole_sheet_and_output(input_path, locale_name, locale_rules, output_name, args_config)
    #print_ipa_process("hwang4", locale_rules, locale_name)
    print("輸出到:", OUTPUT_DIR)