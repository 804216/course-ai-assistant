# mysql3.py
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

# 插入数据
sql = "INSERT INTO student(sno,sname,ssex,sage) VALUES ('%s', '%s', '%s', %d)"
data1 = ('95001','王小明','男',21)
data2 = ('95002','张梅梅','女',20)
cursor.execute(sql % data1)
cursor.execute(sql % data2)
connect.commit()
print('成功插入数据')

# 关闭数据库连接
connect.close()
