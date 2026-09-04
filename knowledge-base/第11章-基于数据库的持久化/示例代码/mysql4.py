# mysql4.py
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

# 修改数据
sql = "UPDATE student SET sage = %d WHERE sno = '%s' "
data = (21, '95002')
cursor.execute(sql % data)
connect.commit()
print('成功修改数据')

# 关闭数据库连接
connect.close()
