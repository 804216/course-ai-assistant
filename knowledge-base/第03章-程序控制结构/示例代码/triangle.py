# triangle.py
rows = int(input('输入行数（奇数）：'))
if rows%2!=0:
    for i in range(0, rows//2+1):
        for j in range(rows-i,0,-1):
            print(" ",end='')
        for k in range(0, 2 * i + 1):
            print("*",end='')
        print("")
    for i in range(rows//2,0,-1):
        for j in range(rows-i+1,0,-1):
            print(" ",end='')
        for k in range(2*i-1,0,-1):
                print("*",end='')
        print("")