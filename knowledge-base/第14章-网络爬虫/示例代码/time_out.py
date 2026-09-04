# time_out.py
import requests
from requests.exceptions import ReadTimeout,ConnectTimeout
try:
   response = requests.get("http://www.baidu.com", timeout=0.5)
   print(response.status_code)
except ReadTimeout or ConnectTimeout:
   print('Timeout')
