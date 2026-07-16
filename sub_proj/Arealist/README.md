# 地点目录 SQL 生成

运行：

```powershell
..\..\.venv\Scripts\python.exe toAreaList.py
```

输出是增量更新：
保留现有 `i_area_list.id`，不 `TRUNCATE`、重新编号或删除未列出的地点。

## AreaList.md 规则

- `sheetname` 为空：只是占位/备注，不写入数据库。
- `emit` 严格等于 `1`：写为隐藏，即 `is_visible=0`。
- `emit` 为空、`2`、`+` 或其他内容：写为显示，即 `is_visible=1`。
- `sort_order` 按有 `sheetname` 的行顺序自动生成 10、20、30……。

移动 Markdown 行并重新生成，可以批量同步排序。临时调整也可以直接在
phpMyAdmin 编辑 `i_area_list.is_visible` 和 `sort_order`；下次导入目录 SQL 时，
会再次以 Markdown 为准。

如果同一个 `first/second/third` 已存在，但 `sheetname` 不同，输出不会把它当成
新地点，而会显示 `AREA_LIST_RENAME_REQUIRED` 和所需命令。先在网站仓库执行：

```bash
php api/scripts/rename_location_table.php --from=旧表名 --to=新表名
php api/scripts/rename_location_table.php --from=旧表名 --to=新表名 --apply
```

重命名后再导入一次 `IAreaList.sql`，最终应显示 `AREA_LIST_OK`。

新地点建议先用 `emit=1` 加入目录，导入并同步字表后再显示。
