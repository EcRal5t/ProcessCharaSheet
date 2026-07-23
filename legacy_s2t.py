"""Compatibility-only OpenCC conversion used by ``--s2t-mode legacy``.

New code must use :mod:`safe_s2t`.  Keeping the old policy in one isolated file
makes its eventual removal mechanical and prevents the exception list from
leaking into parsing or phonological analysis.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chara_struct import Sheet


LEGACY_KEEP_CHARS = {
    "干","后","系","历","板","表","丑","范","丰","刮","胡","回",
    "伙","姜","借","克","困","里","帘","面","蔑","千","秋","松",
    "咸","向","余","郁","御","愿","云","芸","沄","致","制","朱",
    "筑","准","辟","别","卜","斗","谷","划","几","据","卷",
    "了","累","朴","仆","曲","舍","胜","术","台","吁","佣","折",
    "征","症","采","吃","床","峰","杠","恒","栗","秘","凶","熏",
    "肴","占","苧","咨","粽","并","雇","广","么","霉","群","抬",
    "涂","托","涌","游","灶","皂","庄","岩","叶","坏","厘",
    "尸","个","冲","巩","碱","种","岳","于","网","万","糍",
    "夸","荐","杰","晒","痴","姹","麽","昵","蘖","唇","虱","宁",
    "膻","厂",
}


def apply_legacy_s2t(sheet: "Sheet", *, keep_collision: bool, convert_meanings: bool) -> None:
    import opencc

    converter: opencc.OpenCC = opencc.OpenCC("s2t.json")
    sheet.s2t_keeped_char = LEGACY_KEEP_CHARS
    for entry in sheet.entry_list:
        source = entry.chara
        target = converter.convert(source)
        if target == source or source in LEGACY_KEEP_CHARS:
            if target != source:
                logging.debug("%s 簡轉繁未應用 %s -> %s", entry.index, source, target)
            continue
        if target in sheet.chara_index_dict:
            if keep_collision:
                logging.info("%s 簡轉繁保留 %s -> %s", entry.index, source, target)
            else:
                logging.warning("%s 簡轉繁碰撞 %s -> %s", entry.index, source, target)
                entry.status = -1
            continue
        entry.chara = target
        entry.status = 1
        sheet.chara_index_dict[target] = sheet.chara_index_dict.pop(source)
    if convert_meanings:
        sheet.convert_meanings_to_traditional()
