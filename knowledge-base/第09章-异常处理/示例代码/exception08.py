# exception08.py
import sys
print ("当前sys.platform : ",sys.platform)
try:
    assert('unix' in sys.platform),"代码只能在unix下执行。"
    print("unix下执行的代码")
except AssertionError as err:
    print("%s : %s"%(err.__class__.__name__,err))
