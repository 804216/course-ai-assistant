# exception04.py
fname = "d:\\Temp\\info1.log"
try:
    f = open(fname, 'r')
except IOError:
    print('无法打开文件', fname)
else:
    print(fname, '有', len(f.readlines()), '行。')
    f.close()
