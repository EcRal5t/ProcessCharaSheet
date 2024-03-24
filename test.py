import os
import sys
import argparse
from typing import Optional, Set, List, Tuple, Union, Dict

from gr_trasnlator import RULE, split_jpp
from gr_struct import Sheet, Chara


if __name__ == '__main__':
    args_parser = argparse.ArgumentParser(description="jpp 工具    By EcisralHetha")
    args_parser.add_argument('-i', '--input', type=str, help='j++/ipa syllable', required=False)
    args_parser.add_argument('-f', '--filepath', type=str, help='input from file', required=False)
    args_parser.add_argument('-o', "--output", type=str, help='output to file, No specifying for to console', default=None, required=False)
    
    args_parser.add_argument('-l', '--loc', type=str, help='地名', required=False, default='')
    args_parser.add_argument('-m', '--mode', type=str, help='輸出模式', choices=['jpp2ipa', 'ipa2jpp', 'split_jpp'], default='jpp2ipa')
    #args_parser.add_argument('-v', '--version', action='version', version='v0.8/230742')
    
    args_parser.add_argument('-t', '--term', action='store_true', help='未分割的行作輸入')
        
    args_config = args_parser.parse_args()
    syllable: str = args_config.input
    
    if (not syllable and not args_config.filepath) or (syllable and args_config.filepath):
        args_parser.error("-i 和 -f 中需輸入其中一个參數")
    if args_config.mode in ["jpp2ipa", "ipa2jpp"] and not args_config.loc:
        args_parser.error("J++ 和 IPA 互轉時需輸入 -loc 地名參數")
    #print(args_config)
    
    if args_config.output:
        output_filepath = os.path.abspath(args_config.output)
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
        outfile = open(output_filepath, 'w', encoding='utf-8')
    else:
        outfile = sys.stdout
    
    candidate: List[List[str]] = []
    if syllable:
        if args_config.term:
            candidate.append(Sheet.read_row_syllable(syllable.strip().split(","))[1])
        else:
            candidate.append(syllable.strip().split("/"))
    elif args_config.filepath and os.path.exists(args_config.filepath):
        infile = open(args_config.filepath, 'r', encoding='utf-8').readlines()
        for line in infile:
            if args_config.term:
                candidate.append(Sheet.read_row_syllable(line.strip().split(","))[1])
            else:
                candidate.append(line.strip().split("/"))
    else:
        args_parser.error("文件不存在")
    
    if args_config.mode == 'jpp2ipa':
        rule, _ = RULE.select(args_config.loc, [0, 1])
        for syllables in candidate:
            chara: Chara = Chara(0, "_", syllables, "", [])
            chara.to_ipa(rule.j2j, rule.j2i, rule.tone_j2j, rule.tone_j2i)
            print(chara, file=outfile)

    elif args_config.mode == 'ipa2jpp':
        rule, _ = RULE.select(args_config.loc, [0, 1])
        for syllables in candidate:
            chara: Chara = Chara(0, "_", [], "", syllables)
            chara.to_jpp(rule.i2i, rule.i2j, rule.tone_i2j)
            print(chara, file=outfile)

    elif args_config.mode == 'split_jpp':
        for syllables in candidate:
            result: List[List[str]] = []
            for syllable in syllables:
                syllable_s, syllable_t = split_jpp(syllable)
                result.append([syllable_s[0], syllable_s[1]+syllable_s[2], syllable_t])
            result_ = [(i[0] if len(set(i))==1 else "/".join(i)) for i in zip(*result)]
            print(" | ".join(result_), file=outfile)