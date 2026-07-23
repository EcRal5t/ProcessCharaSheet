# 架撐

## 通表用架撐

### 使用 `main.py`

`main.py` 用來轉換字表到數據庫格式

`python main.py -i 字表路径 -l 地名 -n 表名 -c 字頭列 -p 粵拼列 -P 粵拼次音列 -I 音標列 -m 釋義列`

自動化或批處理時可加 `-y`，自動確認由地名讀音推導出的輸出文件名。

只有 `-i` 同 `-c` 必填，`-p`、`-I` 任一必填，`-l`、`-n` 依情況可省

`-n` 默認 `主表` 即調搽表樣式

`-l` 在字表文件名爲「地名(空格)(隨便什麼東西).xlsx」時可省

#### 中古音審計與安全簡繁

加 `--audit-mc` 會在 SQL 轉換前建立本地方言與中古音的概率對應，直接在
控制台打印一張去重的人工複核候選表，不生成審計文件。表中列出音節、聲母、
韻母、聲調相對各自 P99 正常上限高出的 bits，以及模型推測的聲韻調。
同一中古地位可以保留多個現代音節模式。只在至少六個其他字中重複、且正向
常見或反向高度專一的聲韻調關係才可作為新層次反饋進模型；每個字的全部讀音
合計權重爲一，避免多音字過度影響統計。
聲母概率按中古聲母、韻攝、等、開合、重紐作分層回退，韻母概率亦加入中古
聲母及聲母組條件；聲調使用中古調類、清濁和聲母組。只以次音形式出現、但在
多個字中反覆與同一主音共現的讀法，可借用主音的中古地位參與下一輪訓練。

加 `--phonology-table` 會導出一份可搜尋、可打印的 HTML，其中包含聲母、韻母
兩張條件熵歸併表。默認文件名是 `地名_中古音與現音對照表.html`，寫入
`-o/--output-dir` 目錄；可用 `--phonology-table-output PATH` 指定完整路徑。
`--no-output` 只停止 SQL 輸出，不會停止 HTML 報表輸出。聲母
表以中古聲母爲根，韻母表以中古韻爲根；中古聲調亦可作爲附加條件，以顯示
清濁、送氣或韻母演變受調類制約的情形。韻母建模時先臨時把現代 `p/t/k`
韻尾映射到同部位的 `m/n/ng`，因此規則的陽聲韻、入聲韻不會僅因正常的韻尾
平行關係而分裂；HTML 亦按映射後的陽聲韻顯示，轄字欄以「陽聲字數+入聲字數」
分開計數。若映射後仍有足夠降熵，才按調類展開。
所有附加地位都須帶來足夠降熵並抵償分支描述成本；現代輸出相同的葉節點會
自動合併。同一條規則若對應多個現代音，HTML 會逐音拆行；每行依轄字數展示
一至五個例字。現代音背景色由音值字串穩定生成，因此同音在兩表中保持同色。
附加地位的重複前綴會以合併單元格呈現。同一地位內佔比低於 40% 的少見音仍
會保留，但會按佔比逐步淡化。例字後的 `\{…\}` 取自原表備註；若該字的多個
讀音只有聲調不同，則不顯示備註。
此選項可單獨使用，也可與 `--audit-mc` 同用。

中古資料使用 qieyun-auto 的 `KwangUon.csv`。可用 `--mc-data PATH` 指定，或設
`JYUTDICT_MC_DATA`；在 Jyutdict 現有目錄結構下也會自動尋找
`字表/qieyun-auto/KwangUon.csv`。

`--s2t-mode` 有五種策略：

- `legacy`：默認值，保持舊 OpenCC + 硬編碼保留表的行為，供舊命令兼容。
- `off`：不處理字頭；`--no-s2t` 是它的兼容寫法。
- `suggest`：只在控制台打印建議，不改輸出 Entry。
- `copy`：保留原 Entry，另複製一個字頭改為繁體的 Entry。
- `move`：把滿足全部安全條件的 Entry 改名為繁體。

安全模式只採用版本化的嚴格規範簡繁表，不採用異體字列。訓練時排除所有待判
簡化字；只有整個 Entry 的所有讀音都通過總分及聲、韻、調分項 P95、無註釋、
繁體目標唯一、顯著勝過原字且目標未在表內時，`copy/move` 才會生效。部分多音
通過時只報告，不自動拆 Entry。

例如只審計並預覽安全簡繁：

`python main.py -i "梧州戎墟 260714.xlsx" -c A -p e -I j -m b --audit-mc --s2t-mode suggest`

例如額外查看音系歸併表：

`python main.py -i "湛江赤坎 260711.xlsx" -c H -p MNO -P PQR -m S --phonology-table`

確認報告後，如需保留簡體並複製安全繁體 Entry：

`python main.py -i "梧州戎墟 260714.xlsx" -c A -p e -I j -m b --s2t-mode copy`

`--audit-limit` 控制控制台最多打印多少條，默認 200。`--no-output`
只停止 SQL 輸出，不影響控制台審計或音系 HTML。

#### 例

![例1](doc_img/例2.png "順德表，粵拼")

`python main.py -i "順德大良 211021.xlsx" -c A -p B -m C -l 順德`

![例2](doc_img/例1.png "中山表，有音標無粵拼")

`python main.py -i "中山石歧 230915.xlsx" -c H -I MNO -m S`

![例3](doc_img/例3.png "桂平表，有另讀")

`python main.py -i "桂平 220525.xlsx" -c A -p B -m C -P D`

![例3](doc_img/例4.png "江門白話表，另帶音標")

`python main.py -i "江門白話 230910.xlsx" -c H -p NOP -m M -I WXY`

*列號超過 Z 的，自行解決*

導出得一個 .sql 文件，然後登入服務器數據庫，在 jyutdict 庫內 import 便是

生成的地點表會自帶兩個網站查詢索引：`chara` 查字索引，以及
`initial + nuclei + coda` 查音索引；導入完成後會自動執行
`ANALYZE TABLE` 更新統計信息。生成 SQL 會先把全部資料寫入
`表名__new`，成功後使用一次 `RENAME TABLE` 原子替換正式表；若批量
INSERT 中途失敗，原正式表不會被清空或只剩半份資料。
所有普通文字值直接以可閱讀的 UTF-8 輸出；只有引號、反斜線或控制字符才會
局部使用 `CHAR(...)`，因此仍不依賴服務器的 `NO_BACKSLASH_ESCAPES` 設置。

如果目標數據庫中的同名表是由舊版腳本建立，`CREATE TABLE IF NOT EXISTS`
不會補建新索引；需先在網站倉庫執行一次：

`php api/scripts/lookup_indexes.php --apply`

網站部署統一地點讀音表及同步隊列後，舊地點表仍是 Excel SQL 的導入入口。
生成的 SQL 只有在行數校驗及原子換表成功後才會自動寫入
`common_sync_queue`，服務器 cron 隨後同步統一表；在 phpMyAdmin 每次應確認
最後一行同時顯示 `IMPORT_OK` 和 `QUEUED`，無需再逐表登入服務器執行 PHP。

`QUEUE_NOT_INSTALLED` 表示服務器尚未安裝新版隊列表；`QUEUE_AREA_NOT_FOUND`
表示輸出表名與 `i_area_list.sheetname` 不一致。同步失敗時網站統一表會保留
導入前的完整狀態；不要手工修改 `common_entries`。

### 配置音系 jgzw 數據

上面 IPA 與 J++ 之間的轉換、IPA 及 J++ 的後處理、聲調轉換的數據放在 `rules` 文件夾下

- `rule_j2i.csv`: 將 J++ 轉到 IPA
- `rule_i2j.csv`: 將 IPA 轉到 J++
- `rule_j2j.csv`: 修改 J++，應用在 j2i 之後
- `rule_i2i.csv`: 修改 IPA，應用在 i2j 之後
- `rule_tone_j2i.yaml`: 將 J++ 調號轉爲 IPA 調值
- `rule_tone_j2j.yaml`: 修改 J++ 調號，應用在 `tone_j2i` 之前

#### 前四個：音節轉換

音節轉換每行記錄一個轉換規則，形如`化州,*,e,*,*,e̯ɛ,*`、`鬱林,z,e,,*,ⁱᴇ,*`、`蒙山,*,o,t|n,*,ɔª,*`、`1,kʰ,uɐi,*,kʷʰ,ɐi,*」`，表示「規則名,轉換前聲母,轉換前韻*核*,轉換前韻*尾*,轉換後聲母,轉換後韻*核*,轉換後韻*尾*,」

「規則名」用於標記一套規則。上面命令行在默認情況下「`-l XX`」可以引用規則名「XX」「0」「1」三套規則

規則內，「*」指匹配所有，「|」可匹配多項。`化州,*,e,,*,e̯ɛ,*` 指將「…e…」轉換爲「…e̯ɛ…」；`鬱林,z,e,,*,ⁱᴇ,*` 指將「ze」轉換爲「…ⁱᴇ…」；`蒙山,*,o,t|n,*,ɔª,*` 指將「…o(t/n)」轉換爲「…ɔª…」。有順序，見 `rule_j2i.csv` 高州幾行

#### 後二個：聲調轉換

懶得寫了，自己打開看

### `test.py`

測試 jgzw 用的。例: `python test.py -i hai1 -l 廣州`

## 粵表用架撐

使 `sub_proj\PSheet\PanJSheet2Sql.py`

從 google 下載到泛粵表，在上面 python 腳本開頭改 `input_path` 同 `output_dir`，再 `python 佢` 得到三個 .sql 文件

然後按照 `手動屏蔽.yaml`（有兩個是因爲不記得哪個能刪完） 用 `Ctrl+H` *人工*替換掉兩個 `JFaamjyut`

最後入服務器 jyutdict 庫，刪掉同名即 `IFaamjyut` `JFaamjyut` 兩張表，再 import 上面三個文件
