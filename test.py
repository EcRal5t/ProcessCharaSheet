import argparse
import os
import sys
from jpp_trasnlator import *

def get_ipa_from_raw(syllable, locale_rules, locale_name):
    syllable_splited = []
    try:
        syllable_splited = splite_jpp(syllable)
        ipa = get_ipa(locale_rules, syllable_splited, locale_name)
        return syllable_splited, ipa
    except TypeError as e:
        print("含有不合法拼音或未兼容音素 ", syllable_splited, e)
        raise e


if __name__ == '__main__':
    args_parser = argparse.ArgumentParser(description="jpp 工具    By EcisralHetha")
    args_parser.add_argument('-j', '--jpp', type=str, help='j++ syllable', required=False)
    args_parser.add_argument('-i', '--input', type=str, help='input from file', required=False)
    args_parser.add_argument('-o', "--output", type=str, help='output to file, No specifying for to console', default=None, required=False)
    
    args_parser.add_argument('-l', '--loc', type=str, help='地名', required=False, default='')
    args_parser.add_argument('-m', '--mode', type=str, help='輸出模式', choices=['jpp2ipa', 'split_jpp'], default='jpp2ipa')
    #args_parser.add_argument('-v', '--version', action='version', version='v0.5/211017')
    
    args_config = args_parser.parse_args()
    syllable = args_config.jpp
    locale_rules = [0, 1, args_config.loc]
    
    if (not syllable and not args_config.input) or (syllable and args_config.input):
        args_parser.error("-j 和 -i 中需輸入其中一个參數")
    if args_config.mode in ["jpp2ipa"] and not args_config.loc:
        args_parser.error("轉爲 ipa 時需輸入 -loc 地名參數")
    #print(args_config)
    
    if args_config.output:
        output_filepath = os.path.abspath(args_config.output)
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
        outfile = open(output_filepath, 'w', encoding='utf-8')
    else:
        outfile = sys.stdout
    
    candidate: List[str] = []
    if syllable:
        candidate.append(syllable)
    elif args_config.input and os.path.exists(args_config.input):
        infile = open(args_config.input, 'r', encoding='utf-8').readlines()
        candidate.extend([line.strip() for line in infile])
    else:
        args_parser.error("文件不存在")
    
    if args_config.mode == 'jpp2ipa':
        for syllable in candidate:
            syllable_splited, ipa = get_ipa_from_raw(syllable, locale_rules, args_config.loc)
            output_str = f"{syllable} -> {syllable_splited} -> {ipa} -> {format_ipa(ipa)}"
            print(output_str, file=outfile)
    elif args_config.mode == 'split_jpp':
        for syllable in candidate:
            syllable_splited = splite_jpp(syllable)
            print("\t".join(syllable_splited), file=outfile)