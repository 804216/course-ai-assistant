# mysql2.py
import pymysql.cursors

# 连接数据库
connect = pymysql.Connect(
    host='localhost',
    port=3306,
    user='root',  # 数据库用户名
    passwd='123456',  # 密码
    db='school',
    charset='utf8'
)

# 获取游标
cursor = connect.cursor()

# 如果表存在，则先删除
cursor.execute("DROP TABLE IF EXISTS student")

# 设定SQL语句

sql = """
create table student(
    sno char(5),
    sname char(10),
    ssex char(2),
    sage int);
"""

# 执行SQL语句
cursor.execute(sql)

# 关闭数据库连接
connect.close()
