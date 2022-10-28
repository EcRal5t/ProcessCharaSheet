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


if __name__ == '__main__':
    args_parser = argparse.ArgumentParser(description="一鍵轉換jpp    By EcisralHetha")
    args_parser.add_argument('jpp', type=str, help='j++ format')
    args_parser.add_argument('loc', type=str, help='地名')
    #args_parser.add_argument('-v', '--version', action='version', version='v0.5/211017')
    args_config = args_parser.parse_args()
    #print(args_config)
    
    locale_rules = [0, 1, args_config.loc]
    
    print_ipa_process(args_config.jpp, locale_rules, args_config.loc)