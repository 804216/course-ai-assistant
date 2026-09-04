# baidu_hot.py
import requests
from bs4 import BeautifulSoup

# 请求网页
def request_page(url,headers):
    response = requests.get(url,headers=headers)
    response.encoding = response.apparent_encoding 
    return response.text


# 解析网页
def parse_page(html):
    soup = BeautifulSoup(html,'html.parser')
    all_topics=soup.find_all('tr')[1:]
    for each_topic in all_topics:        
        topic_times = each_topic.find('td',class_='last')    #搜索指数
        topic_rank = each_topic.find('td',class_='first')    #排名
        topic_name = each_topic.find('td',class_='keyword')  #标题
        if topic_rank != None and topic_name!=None and topic_times!=None:
            topic_rank = each_topic.find('td',class_='first').get_text().replace(' ','').replace('\n','')
            topic_name = each_topic.find('td',class_='keyword').get_text().replace(' ','').replace('\n','')
            topic_times = each_topic.find('td',class_='last').get_text().replace(' ','').replace('\n','')            
            tplt = "排名：{0:^4}\t标题：{1:{3}^15}\t热度：{2:^8}"
            print(tplt.format(topic_rank,topic_name,topic_times,chr(12288)))    

if __name__=='__main__':
    url = 'http://top.baidu.com/buzz?b=1&fr=20811'
    headers = {'User-Agent':'Mozilla/5.0'}
    html = request_page(url,headers)
    parse_page(html)
