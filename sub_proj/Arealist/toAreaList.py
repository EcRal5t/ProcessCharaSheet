import io
import pandas as pd

def sql_escape(s: str) -> str:
    """
    Escapes single quotes in a string for SQL insertion.
    ' -> ''
    """
    return s.replace("'", "''")

def markdown_to_sql(markdown_table: str, table_name: str = "IAreaList") -> str:
    """
    将Markdown表格字符串转换回SQL INSERT语句。
    - 假定 'emit' 是最后一列。
    - 空单元格将保持为空字符串。
    
    Args:
        markdown_table: Markdown格式的表格字符串。
        table_name: SQL表名。

    Returns:
        完整的SQL INSERT语句字符串。
    """
    if not markdown_table.strip():
        return f"-- Markdown input is empty. No SQL generated for {table_name}."

    try:
        # 使用 StringIO 将字符串模拟成文件，以便 pandas 读取
        # sep='|' 表示使用竖线作为分隔符
        # skipinitialspace=True 可以处理竖线后的空格
        df = pd.read_csv(io.StringIO(markdown_table.strip()), sep='|', skipinitialspace=True)
    except Exception as e:
        return f"-- Error parsing Markdown table: {e}"

    # 1. 清理DataFrame
    # 删除因首尾竖线产生的空白列
    df = df.iloc[:, 1:-1]
    # 清理列名的前后空格
    df.columns = [col.strip() for col in df.columns]
    # 删除Markdown的分隔线行 (e.g., |:---|:---|)
    df = df.drop(0).reset_index(drop=True)

    # 2. 【关键修改】将所有 NaN 值替换为空字符串 ""
    df.fillna('', inplace=True)

    # 3. 根据最后一列 ('emit') 的值进行过滤
    # .astype(str) 确保即使是数字1也能被正确比较
    last_col_name = df.columns[-1]
    df_filtered = df[df[last_col_name].astype(str).str.strip() != '1']

    # 如果过滤后没有数据，则返回提示
    if df_filtered.empty:
        return f"-- No data to insert into {table_name} after filtering."
        
    # 4. 准备生成 SQL
    # 去掉用于过滤的 emit 列
    df_final = df_filtered.iloc[:, :-1]
    
    sql_values = []
    for _, row in df_final.iterrows():
        # 将行数据转换为列表
        row_values = list(row)
        
        # 准备要插入的值，并进行格式化
        # id 固定为 0
        id_val = "0"
        # 经纬度是数字，不需要引号
        long_val = row_values[0] if row_values[0] != '' else '0'
        lat_val  = row_values[1] if row_values[1] != '' else '0'
        # 其他列是字符串，需要加引号并转义
        first_val     = f"'{sql_escape(row_values[2].strip())}'"
        second_val    = f"'{sql_escape(row_values[3].strip())}'"
        third_val     = f"'{sql_escape(row_values[4].strip())}'"
        sheetname_val = f"'{sql_escape(row_values[5].strip())}'"
        color_val     = f"'{sql_escape(row_values[6].strip())}'"

        value_tuple_str = f"({long_val}, {lat_val}, {first_val}, {second_val}, {third_val}, {sheetname_val}, {color_val})"
        sql_values.append(value_tuple_str)

    # 组装完整的 SQL 语句
    sql_header = """
    CREATE TABLE `{IAreaList}` (
  `id` int NOT NULL,
  `longitude` double NOT NULL,
  `latitude` double NOT NULL,
  `first` tinytext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `second` tinytext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `third` tinytext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `sheetname` tinytext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `color` tinytext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE `{IAreaList}` ADD PRIMARY KEY(`id`);
ALTER TABLE `{IAreaList}` CHANGE `id` `id` INT(11) NOT NULL AUTO_INCREMENT;"""

    sql_header = """TRUNCATE TABLE `{IAreaList}`;
INSERT INTO `{IAreaList}` (`longitude`, `latitude`, `first`, `second`, `third`, `sheetname`, `color`) VALUES
""".lstrip().replace('{IAreaList}', table_name)
    sql_body = ',\n'.join(sql_values)
    
    return sql_header + sql_body + ';'

if __name__ == '__main__':
    import pathlib
    with open(pathlib.Path(__file__).parent / 'AreaList.md', 'r', encoding='utf-8') as f:
        markdown_data = f.read()
    generated_sql = markdown_to_sql(markdown_data)
    with open(pathlib.Path(__file__).parent / 'IAreaList.sql', 'w', encoding='utf-8') as f:
        f.write(generated_sql)
