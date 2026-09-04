# crawl_poem.py
import requests
from bs4 import BeautifulSoup
import time
import json

# 函数1：请求网页
def page_request(url, ua):
    # 修改为处理重定向后的URL
    response = requests.get(url, headers=ua, allow_redirects=True)
    html = response.content.decode('utf-8')
    return html

# 函数2：解析网页
def page_parse(html):
    soup = BeautifulSoup(html, 'lxml')
    info = soup.select('div.sons div.cont')
    sentence_list = []
    href_list = []
    
    for item in info:
        # 提取诗句文本
        poem_text = item.find('a').get_text(strip=True)       
        # 提取出处
        source = item.select('a:nth-child(3)')
        if len(source) == 0:
            continue
        poem_source = source[0].get_text()       
      
        # 组合信息
        poem_info = f"{poem_text} —— {poem_source}"
        sentence_list.append(poem_info)
        
        # 提取链接
        href = item.find('a')['href']
        # 注意这里链接可能需要调整
        href_list.append("https://www.gushiwen.cn" + href if not href.startswith('http') else href)
    
    return [href_list, sentence_list]

def save_txt(info_list):
    with open(r'sentence.txt', 'a', encoding='utf-8') as txt_file:
        for element in info_list[1]:
            txt_file.write(element + '\n\n')

# 子网页处理函数：进入并解析子网页/请求子网页
def sub_page_request(info_list):
    subpage_urls = info_list[0]
    ua = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/46.0.2490.86 Safari/537.36'}
    sub_html = []
    for url in subpage_urls:
        html = page_request(url, ua)
        sub_html.append(html)
        time.sleep(1)  # 添加延迟防止被封
    return sub_html

# 子网页处理函数：解析子网页，爬取诗句内容
def sub_page_parse(sub_html):
    poem_list = []
    for html in sub_html:
        soup = BeautifulSoup(html, 'lxml')
        poem = soup.find('div', class_='contson')
        if poem:
            poem_list.append(poem.get_text().strip())
    return poem_list

# 子网页处理函数：保存诗句到txt
def sub_page_save(poem_list):
    with open(r'poems.txt', 'a', encoding='utf-8') as txt_file:
        for element in poem_list:
            txt_file.write(element + '\n\n')

if __name__ == '__main__':
    print("**************开始爬取古诗文网站********************")
    ua = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/46.0.2490.86 Safari/537.36'}
    poemCount = 0
    poem_list_all = []  # 用于保存所有诗词
    
    # 修改为使用重定向后的URL
    base_url = 'https://www.gushiwen.cn/mingjus/default.aspx?page=%d'
    
    for i in range(1, 3):  # 一共爬取2页
        url = base_url % i
        print("正在爬取:", url)
        html = page_request(url, ua)
        info_list = page_parse(html)
        save_txt(info_list)
        # 开始处理子网页
        print("开始解析第%d" % i + "页")
        # 开始解析名句子网页
        sub_html = sub_page_request(info_list)
        poem_list = sub_page_parse(sub_html)
        poem_list_all.extend(poem_list)
        sub_page_save(poem_list)
        poemCount += len(info_list[0])
        time.sleep(2)  # 添加延迟防止被封
    
    print("****************爬取完成***********************")
    print("共爬取%d" % poemCount + "个古诗词名句")
    print("共爬取%d" % len(poem_list_all) + "个古诗词")
