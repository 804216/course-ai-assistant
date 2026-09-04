#program_process.py
import time
scale = 40
print('执行开始')
start = time.perf_counter()
for i in range(scale+1):
  a = '*' * i
  b = '.' * (scale - i)
  c = (i / scale) * 100
  dur = time.perf_counter() - start
  print("\r{:^3.0f}%[{}->{}]{:.2f}".format(c,a,b,dur))
  time.sleep(0.1)
print('\n'+'执行结束')
