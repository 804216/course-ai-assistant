# continue2.py
sum = 0
x = 0
while True:
  x = x + 1
  if x > 100:
    break
  if x % 2 == 0:
    continue
  sum += x
print(sum)
