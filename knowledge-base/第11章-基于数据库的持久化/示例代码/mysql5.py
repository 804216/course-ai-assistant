# mysql5.py
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

# 查询数据
sql = "SELECT sno,sname,ssex,sage FROM student WHERE sno = '%s' "
data = ('95001',)    #元组中只有一个元素的时候需要加一个逗号
cursor.execute(sql % data)
for row in cursor.fetchall():
    print("学号:%s\t姓名:%s\t性别:%s\t年龄:%d" % row)
print('共查找出', cursor.rowcount, '条数据')

# 关闭数据库连接
connect.close()
