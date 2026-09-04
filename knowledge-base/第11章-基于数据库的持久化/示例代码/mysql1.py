# mysql1.py
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

# 执行SQL查询
cursor.execute("SELECT VERSION()")

# 获取单条数据
version = cursor.fetchone()

# 打印输出
print("MySQL数据库版本是：%s" % version)

# 关闭数据库连接
connect.close()
