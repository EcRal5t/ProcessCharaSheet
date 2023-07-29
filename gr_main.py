import gradio as gr
import pandas as pd
import openpyxl

from typing import Optional, Any, List, Tuple, Dict, Callable, Union
import argparse
from functools import reduce
import time
import logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s | %(funcName)s: %(levelname)s] %(message)s')

from gr_struct import *

SHEETS: List[Sheet] = []
SHEET_IDX: int = 0
SHEET_RAW: pd.ExcelFile
def parse_sheet(df: pd.DataFrame, 
                locate: str, append_rule: List[Union[str, int]], 
                char_col : int,
                pron_cols: List[int],
                mean_cols: List[int],
                ipa_cols : List[int],
                pron_nd_cols: List[int],
                no_sim_to_trad: bool, keep_sim_to_trad: bool
                ) -> str:
    global SHEETS, SHEET_IDX
    s = Sheet(df, locate, append_rule, 
            char_col,
            pron_cols, 
            mean_cols,
            ipa_cols,
            pron_nd_cols,
            no_sim_to_trad, keep_sim_to_trad)
    if len(SHEETS) <= SHEET_IDX:
        SHEETS.append(s)
        SHEET_IDX = len(SHEETS)-1
    else:
        SHEETS[SHEET_IDX] = s
    return ""

def log(fn_name: str, msg: str, level: str="INFO"):
    return f"[{time.strftime('%Y-%m-%d %H:%M:%S')} | {fn_name}: {level}] {msg}\n"

def l_set_sheet_names_by_file(xls_file: gr.File):
    if xls_file is None:
        return in_opt_sheet_name.update(choices=[])
    else:
        return l_set_sheet_names_by_file_path(xls_file.name) # type: ignore

def l_set_sheet_names_by_file_path(xls_file_path: str):
    global SHEET_RAW
    SHEET_RAW = pd.ExcelFile(xls_file_path)
    logging.info(f'所有表名: {SHEET_RAW.sheet_names}')
    assert isinstance(SHEET_RAW.book, openpyxl.Workbook), "SHEET_RAW.book 不是 openpyxl.Workbook"
    return in_opt_sheet_name.update(
        choices = [str(i) for i in SHEET_RAW.sheet_names], 
        value = SHEET_RAW.book.active.title  # type: ignore
            if SHEET_RAW.book.active is not None and SHEET_RAW.book.active.title in SHEET_RAW.sheet_names
            else str(SHEET_RAW.sheet_names[0])
    )

def l_set_locate_name_by_opt_sheet_name(sheet_name: str):
    if sheet_name is None:
        return in_opt_locate_name.update(value="")
    return in_opt_locate_name.update(value=sheet_name.strip())

def show_sheet_first_row_(sheet_name: str, console_log: str) -> str:
    if sheet_name not in SHEET_RAW.sheet_names:
        return console_log + log("讀取表頭", f"無此表名: {sheet_name}", "ERROR")
    else:
        assert isinstance(SHEET_RAW.book, openpyxl.Workbook), "SHEET_RAW.book 不是 openpyxl.Workbook"
        first_row = SHEET_RAW.book.worksheets[SHEET_RAW.sheet_names.index(sheet_name)]["A1:Z1"][0]
        first_row_filter = filter(lambda x: getattr(x, "value", None) is not None, first_row)
        first_row_strs = [f'{i.coordinate}: {i.value}' for i in first_row_filter]
        return console_log + log("讀取表頭", f"{sheet_name} 表首行: {', '.join(first_row_strs)}")

def l_parse_sheet(sheet_name: str, locate: str, append_rule_: str, 
                col_char: str,
                col_pron: str, col_mean: str,
                col_ipa: str, col_pron_nd: str, 
                no_sim_to_trad: bool, keep_sim_to_trad: bool, msg_: str, 
                sheet_idx: int=0) -> Tuple[str, Dict]:
    if sheet_name not in SHEET_RAW.sheet_names:
        return log("解析表", f"無此表名: {sheet_name}", "ERROR"), in_btn_read_rule_file.update()
    if col_char == "":
        return log("解析表", f"未設置字頭列", "ERROR"), in_btn_read_rule_file.update()
    if col_pron == "" and col_ipa == "":
        return log("解析表", f"未設置讀音列", "ERROR"), in_btn_read_rule_file.update()
    f = SHEET_RAW.parse(SHEET_RAW.sheet_names.index(sheet_name), keep_default_na=False, dtype=str)
    parse_sheet(f, locate.strip(), append_rule_.split(","), # type: ignore
                get_col_index(col_char), 
                [get_col_index(col_pron)    for col_pron    in col_pron   .replace(" ", "").replace(",", "")],
                [get_col_index(col_mean)    for col_mean    in col_mean   .replace(" ", "").replace(",", "")],
                [get_col_index(col_ipa)     for col_ipa     in col_ipa    .replace(" ", "").replace(",", "")],
                [get_col_index(col_pron_nd) for col_pron_nd in col_pron_nd.replace(" ", "").replace(",", "")],
                no_sim_to_trad, keep_sim_to_trad
    )
    
    return SHEETS[SHEET_IDX].get_log()+"\n"+msg_, in_btn_read_rule_file.update(interactive=True)
    
def l_read_locale_rule(locate_: str, append_rule_: str, msg_: str, ) -> str:
    locate = locate_.strip()
    append_rule = append_rule_.split(",")
    msg_0 = RULE.reload()
    SHEETS[SHEET_IDX].rule, msg_1 = RULE.select(locate, append_rule) # type: ignore
    return log("讀取轉換規則檔", f"在 {locate} + {append_rule} 中讀取. {msg_0}, {msg_1}") + "\n" + msg_
    
def get_col_index(colname: str) -> int:
    if colname.isdigit():
        return int(colname)
    elif len(colname)>1:
        r = [get_col_index(i) for i in colname.replace(" ", "").replace(",", "") if i != ""]
        logging.warning(f"多個欄位名: {colname}，取第一個: {r[0]}")
        return r[0]
    elif colname.isupper():
        return ord(colname)-65
    else:
        return ord(colname)-97
        
        
def translit_chs_to_jpp(chs: str) -> Tuple[str]:
    presence = SHEETS[SHEET_IDX].show_str_to_jpp(chs)
    msg = ""
    return (presence, )

def l_output_file(path: str, name_jpp: str, overwrite: bool, msg_: str) -> str:
    msgs: List[str] = []
    path = os.path.abspath(path)
    if os.path.isdir(path):
        path = os.path.join(path, "Z"+name_jpp+".sql")
        msgs.append(log("輸出檔案", f"將輸出到: {path}"))
    if not os.path.exists(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    if os.path.isfile(path) and not overwrite:
        return log("輸出檔案", f"檔案已存在: {path}", "ERROR")
    # if not os.access(path, os.W_OK):
    #     return log("輸出檔案", f"檔案無法寫入: {path}", "ERROR")
    if os.path.isfile(path) and overwrite:
        msgs.append(log("輸出檔案", f"檔案已存在: {path}", "WARNING"))
    with open(path, "w", encoding="utf-8") as f:
        chara_count, pron_count, content = SHEETS[SHEET_IDX].output_sql_full("Z"+name_jpp)
        f.write(content)
    msgs.append(log("輸出檔案", f"輸出成功: {path}, 計 {chara_count} 字, {pron_count} 音"))
    return "\n".join(msgs) + "\n" + msg_

with gr.Blocks(
    theme=gr.themes.Base(
        primary_hue = gr.themes.colors.green,
        font=["Source Sans Pro", "Arial", "sans-serif"],
        font_mono=['JetBrains mono', "Consolas", 'Courier New']
    ),
) as app:
    with gr.Tabs():
        with gr.Row():
            with gr.Column():
                with gr.TabItem("上傳"):
                    in_file_upload = gr.File(
                        label="上傳字表",
                        interactive=True,
                        file_types=["xlsx", "xls"],
                    )
                with gr.TabItem("輸入路徑"):
                    with gr.Column(scale=5):
                        in_file_path = gr.Textbox(label="字表路徑", interactive=True)
                    with gr.Column(scale=1, min_width=40):
                        in_btn_file_read = gr.Button(value="讀取字表")
                with gr.Row():
                    with gr.Column(scale=5):
                        in_opt_sheet_name = gr.Dropdown(label="字表所在頁", interactive=True)
                    with gr.Column(scale=1, min_width=40):
                        in_btn_set_sheet_names = gr.Button(value="寫入地名")
                        in_btn_read_first_row = gr.Button(value="讀取表頭")
                ou_export_dir = gr.Textbox(value="./result", label="輸出目錄")
            with gr.Column():
                with gr.Row():
                    in_opt_locate_name = gr.Textbox(label="地名", interactive=True)
                    in_opt_rule_j2i_supl = gr.Textbox(value="0,1", label="補充轉寫規則", interactive=True)
                    in_btn_read_rule_file = gr.Button(value="讀取規則檔", interactive=False)
                with gr.Row():
                    in_opt_col_char = gr.Textbox(label="漢字字頭所在列(必填)", interactive=True)
                    in_opt_col_pron = gr.Textbox(label="拼音所在列(選填)", interactive=True)
                    in_opt_col_prnd = gr.Textbox(label="次音所在列(選填)", interactive=True)
                    in_opt_col_mean = gr.Textbox(label="釋義所在列(選填)", interactive=True)
                    in_opt_col_ipa  = gr.Textbox(label="IPA 所在列(選填)", interactive=True)
                with gr.Row():
                    in_opt_no_s2t   = gr.Checkbox(label="不進行簡轉繁")
                    in_opt_keep_s2t = gr.Checkbox(label="簡轉繁時保留衝突的簡體字")
                    in_opt_is_debug = gr.Checkbox(label="除錯模式")
                    in_opt_output_overwrite = gr.Checkbox(label="輸出時覆蓋", value=True)
                in_btn_parse_sheet = gr.Button(value="解析字表")
        with gr.Row():
            with gr.Column():
                ou_console = gr.Textbox(label="處理結果", lines=4, interactive=False, max_lines=4)
            with gr.Column():
                in_test_text = gr.Textbox(label="測試文本", interactive=True)
                in_btn_get_test_text_trans = gr.Button(value="轉換")
                ou_test_text = gr.Textbox(label="轉換結果", lines=4, interactive=False, max_lines=4)
            with gr.Column():
                in_opt_output_path = gr.Textbox(value=os.path.join(os.path.dirname(__file__), "output"), label="輸出路徑", interactive=True)
                in_opt_locate_jpp = gr.Textbox(label="地名的 J++ 轉寫", interactive=True)
                in_btn_output = gr.Button(value="輸出")
            
    in_file_upload.change(l_set_sheet_names_by_file, [in_file_upload], [in_opt_sheet_name])
    in_btn_file_read.click(l_set_sheet_names_by_file_path, [in_file_path], [in_opt_sheet_name])
    in_btn_set_sheet_names.click(l_set_locate_name_by_opt_sheet_name, [in_opt_sheet_name], [in_opt_locate_name])
    in_btn_read_first_row.click(show_sheet_first_row_, [in_opt_sheet_name, ou_console], [ou_console])
    in_btn_parse_sheet.click(l_parse_sheet, [in_opt_sheet_name, in_opt_locate_name, in_opt_rule_j2i_supl, in_opt_col_char, in_opt_col_pron, in_opt_col_mean, in_opt_col_ipa, in_opt_col_prnd, in_opt_no_s2t, in_opt_keep_s2t, ou_console], [ou_console, in_btn_read_rule_file])
    in_btn_get_test_text_trans.click(translit_chs_to_jpp, [in_test_text], [ou_test_text])
    in_btn_output.click(l_output_file, [in_opt_output_path, in_opt_locate_jpp, in_opt_output_overwrite, ou_console], [ou_console])
    in_btn_read_rule_file.click(l_read_locale_rule, [in_opt_locate_name, in_opt_rule_j2i_supl, ou_console], [ou_console])
    
    
    logging.info(f"當前工作目錄: {os.getcwd()}")
    app.launch()

