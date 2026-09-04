# html_to_mysql.py
import requests
from bs4 import BeautifulSoup

# 读取本地HTML文件
def get_html():
    path = 'C:/web_demo.html'
    htmlfile= open(path,'r')
    html = htmlfile.read()
    return html

# 解析HTML文件
def parse_html(html):
    soup = BeautifulSoup(html,'html.parser')
    all_tr=soup.find_all('tr')[1:]
    all_tr_list = []
    info_list = []
    for i in range(len(all_tr)):
        all_tr_list.append(all_tr[i])
    for element in all_tr_list:
        all_td=element.find_all('td')
        all_td_list = []
        for j in range(len(all_td)):
            all_td_list.append(all_td[j].string)
        #print(all_td_list)
        info_list.append(all_td_list)
    return info_list

# 保存数据库
def save_mysql(info_list):
    import pymysql.cursors
    # 连接数据库
    connect = pymysql.Connect(
        host='localhost',
        port=3306,
        user='root',  # 数据库用户名
        passwd='123456',  # 密码
        db='webdb',
        charset='utf8'
    )

    # 获取游标
    cursor = connect.cursor()
    
    # 插入数据
    for item in info_list:
        id = int(item[0])
        keyword = item[1]
        number = int(item[2])
        sql = "INSERT INTO search_index(id,keyword,number) VALUES ('%d', '%s', %d)"
        data = (id,keyword,number)
        cursor.execute(sql % data)
        connect.commit()
    print('成功插入数据')

    # 关闭数据库连接
    connect.close()
    
if __name__ =='__main__':
    html = get_html()
    info_list = parse_html(html)
    save_mysql(info_list)
