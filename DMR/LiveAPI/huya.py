import random
try:
    from .BaseAPI import BaseAPI
except ImportError:
    from BaseAPI import BaseAPI
import requests
import re
import base64
from lxml import etree
import urllib.parse
import hashlib
import time
import logging

class huya(BaseAPI):
    header = {
            'Content-Type': 'application/x-www-form-urlencoded',
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36 Edg/88.0.705.68",
        }
    header_mobile = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 5.0; SM-G900P Build/LRX21T) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/75.0.3770.100 Mobile Safari/537.36 '
        }
    def __init__(self,rid:str) -> None:
        self.rid = rid
        if not self.rid.isdigit():
            try:
                response = self._get_response()
                selector = etree.HTML(response)
                self.rid = selector.xpath('//*[@class="host-rid"]/em')[0].text
            except:
                pass
    
    def _get_response(self,mobile=False):
        if not mobile:
            room_url = 'https://www.huya.com/' + self.rid
            response = requests.get(url=room_url, headers=self.header).text
        else:
            room_url = 'https://m.huya.com/' + self.rid
            response = requests.get(url=room_url, headers=self.header_mobile).text
        return response

    def _get_api_response(self):
        room_url = 'https://mp.huya.com/cache.php?m=Live&do=profileRoom&roomid=' + str(self.rid)
        data = requests.get(url=room_url, headers=self.header_mobile).json()
        return data

    def is_available(self) -> bool:
        try:
            response = self._get_response(mobile=True)
            liveLineUrl = re.findall(r'"liveLineUrl":"([\s\S]*?)",', response)[0]
            liveline = base64.b64decode(liveLineUrl).decode('utf-8')
            return True
        except:
            return False

    def onair(self) -> bool:
        try:
            data = self._get_api_response()
            status=data['data']['realLiveStatus']
            if status == 'ON':
                return True
            elif status == 'OFF':
                return False
            else:
                response = self._get_response(mobile=True)
                liveLineUrl = re.findall(r'"liveLineUrl":"([\s\S]*?)",', response)[0]
                liveline = base64.b64decode(liveLineUrl).decode('utf-8')
                if liveline and 'replay' not in liveline:
                    return True
                else:
                    return False
        except Exception as e:
            logging.exception(e)
            return None

    def get_info(self):
        """
        return: title,uname,face_url,keyframe_url
        """
        response = self._get_api_response()
        data = response['data']['liveData']
        try:
            title = data['introduction']
        except:
            title = 'huya'+self.rid
        try:
            uname = data['nick']
        except:
            uname = 'huya'+self.rid
        try:
            face_url = data['avatar180']
        except:
            face_url = None
        try:
            keyframe_url = data['screenshot']
        except:
            keyframe_url = None
        return title,uname,face_url,keyframe_url

    def get_stream_url(self) -> str:
        data = self._get_api_response()
        multiLine=data['data']['stream']['flv']['multiLine']
        urls=[]
        
        for i in range(len(multiLine)):
            obj=multiLine[i]
            if obj['url'] is not None:
                # liveline = live(obj['url'])
                # urls.append(liveline)
                urls.append(obj['url'])
        return {
            'url': urls[0]
        }

if __name__ == '__main__':
    api = huya('17797964')
    print(api.get_info())


        