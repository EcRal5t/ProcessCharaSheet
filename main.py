# encoding: utf-8
# python3
import os
import logging
import argparse
from typing import Optional, Any, List, Tuple, Dict, Callable, Union
from functools import reduce

import pandas as pd

from gr_struct import Sheet, get_col_index
from gr_trasnlator import split_jpp

def retrieve_locale_name(sheet:Sheet, name: str, is_output: bool) -> str:
    charas_prons = sheet.query(name)
    charas_prons_flatten_= [[c_p.prons for c_p in c_ps] for c_ps in charas_prons]
    charas_prons_flatten = [[p for c_p in c_ps for p in c_p] for c_ps in charas_prons_flatten_]
    charas_prons_no_tone = [{"".join(split_jpp(c_p)[0]) for c_p in c_ps} for c_ps in charas_prons_flatten]
    is_op_name_available = True
    op_name = ""
    for n, chara_prons in enumerate(charas_prons_no_tone):
        if len(chara_prons)==0:
            is_op_name_available = False
            logging.warning(f"{name[n]} 未記音")
        elif len(chara_prons) > 1:
            is_op_name_available = False
            logging.warning(f"{name[n]} 有多音: {' | '.join([str(i) for i in charas_prons[n]])}")
        else:
            pron = chara_prons.pop()
            op_name += pron.capitalize() if (n==0 or n==2) else pron
            logging.info(f"{name[n]}: {pron}")
    op_name_ = op_name if is_op_name_available else ""
    
    if is_output:
        if not is_op_name_available: 
            op_name_ = input("地名不滿足 jgzw 條件，需鍵入導出文件名: ")
        while True:
            op_name_ = input(f"回車以確認輸出文件名為 Z{op_name_}.sql，否則請輸入導出名: ")
            if op_name_ == "": break
    else:
        if not is_op_name_available: 
            logging.warning("地名不滿足 jgzw 條件")
        else:
            logging.info(f"輸出文件名將為 Z{op_name_}.sql")
    return "Z" + op_name_


if __name__ == '__main__':
    os.system("cls")
    args_parser = argparse.ArgumentParser(description="從字表轉換到數據庫格式。    By EcisralHetha")
    args_parser.add_argument('-l', '--locale-name', type=str, help='地名，需要包括小地名在內的全名')
    args_parser.add_argument('-i', '--file-path', type=str, required=True,  help='輸入字表路徑')
    args_parser.add_argument('-o', '--output-dir', type=str, default="./output", help='輸出目錄')
    args_parser.add_argument('-n', '--sheet-name', type=str, help='表格所在的表名', default='主表')
    #args_parser.add_argument('-v', '--version', action='version', version='v0.9c/240324')
    args_parser.add_argument('--no-output', action='store_true', help='不輸出 SQL 文件')
    args_parser.add_argument('-c', '--char', type=str, help='字頭所在列', required=True)
    args_parser.add_argument('-p', '--pron', type=str, help='拼音所在列', default="")
    args_parser.add_argument('-P', '--pron_nd', type=str, help='次音所在列', default="")
    args_parser.add_argument('-m', '--mean', type=str, help='釋義所在列', default="")
    args_parser.add_argument('-I', '--ipa', type=str, help='IPA 所在列', default="")
    args_parser.add_argument('--no-s2t', action='store_true', help='不轉換簡體字')
    args_parser.add_argument('--keep-s2t', action='store_true', help='簡轉繁衝突時簡體保留，否則捨棄')
    args_parser.add_argument('--debug', action='store_true', help='顯示詳細資訊')
    args_config = args_parser.parse_args()
    if not args_config.ipa and not args_config.pron:
        args_parser.error("j++ 和 ipa 至少存在一列")
    
    logging.basicConfig(level=logging.DEBUG if args_config.debug else logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
    logging.debug(args_config)
    
    output_dir  = args_config.output_dir
    input_path  = args_config.file_path
    if not args_config.no_output and not os.path.exists(output_dir): os.mkdir(output_dir)
    if not os.path.exists(input_path):
        logging.error("輸入文件不存在")
        exit(1)
    
    locale_name :str = args_config.locale_name if args_config.locale_name else os.path.basename(input_path).split(" ")[0] 
    sheet_name  :str = args_config.sheet_name#"Sheet1"
    
    col_char    :str = args_config.char
    col_pron    :str = args_config.pron
    col_pron_nd :str = args_config.pron_nd
    col_mean    :str = args_config.mean
    col_ipa     :str = args_config.ipa
    
    col_char_idx     =  get_col_index(col_char)
    col_pron_idxs    = [get_col_index(col) for col in col_pron   ]
    col_pron_nd_idxs = [get_col_index(col) for col in col_pron_nd]
    col_mean_idxs    = [get_col_index(col) for col in col_mean   ]
    col_ipa_idxs     = [get_col_index(col) for col in col_ipa    ]
    logging.debug(f"{col_char_idx=}, {col_pron_idxs=}, {col_pron_nd_idxs=}, {col_mean_idxs=}, {col_ipa_idxs=}")
    
    no_sim_to_trad = args_config.no_s2t
    keep_sim_to_trad = args_config.keep_s2t
    
    is_exporting_sql = not args_config.no_output
    
    try:
        logging.info("1____读取文件____")
        data_raw = pd.ExcelFile(input_path)
        logging.info("2____分析文件____")
        data_parsed = data_raw.parse(data_raw.sheet_names.index(sheet_name), keep_default_na=False, dtype=str)

        logging.info("3____分析数据____")
        sheet = Sheet(data_parsed, locale_name, [0, 1],
                col_char_idx,
                col_pron_idxs,
                col_mean_idxs,
                col_ipa_idxs,
                col_pron_nd_idxs,
                no_sim_to_trad, keep_sim_to_trad)
        
        logging.info("4____转换地名____")
        output_name = retrieve_locale_name(sheet, locale_name, is_exporting_sql)
        
        if is_exporting_sql:
            logging.info("5____輸出文件____")
            count_row, count_chara, sql_content = sheet.output_sql_full(output_name)
            logging.info(f"有效 {count_row} 音, {count_chara} 字")
            with open(os.path.join(output_dir, f"{output_name}.sql"), 'w', encoding='utf-8') as f:
                f.write(sql_content)
            
        logging.info("6____完成____")
    except KeyboardInterrupt as e:
        print()
        logging.error("用戶中斷")
    