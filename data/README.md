# Data used by the conservative S2T mode

`s2t_strict.tsv` contains only the simplified-head → traditional-head pairs from
Appendix 1's “繁体字” column of the 2013 *Table of General Standard Chinese
Characters*.  Variant columns are intentionally excluded, so relations such as
`皂→皁` cannot trigger conversion.

The file was generated from `通用规范汉字表.digitalized.xlsx` whose SHA-256 is
`9f45bff2376ded8098e1d1e79cff975406619ec66c5e6308b2716222ca6af7e1`.
Integrity constraints checked at load time: 2,546 source characters and 2,574
source-target pairs.  `source_id` retains the table's source row identifier.

Middle-Chinese data is not bundled.  Supply qieyun-auto's `KwangUon.csv` with
`--mc-data`, set `JYUTDICT_MC_DATA`, or keep it at the sibling Jyutdict location
that `main.py` auto-discovers.
