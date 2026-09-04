# digit.py
prompt = '输入一个数字，我将告诉你，它是奇数，还是偶数'
prompt += '\n输入“结束游戏”，将退出本程序： '
exit = '结束游戏' # 退出指令
content = '' #输入内容
while content != exit:
    content = input(prompt)
    if content.isdigit():    #isdigit()函数用于检测字符串是否只由数字组成
        number = int(content)
        if (number % 2 == 0):
            print('该数是偶数')
        else:
            print('该数是奇数')
    elif content != exit:
        print('输入的必须是数字')
