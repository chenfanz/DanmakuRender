import logging
import os
import re
import threading
import sys
import tempfile
import time
import subprocess
import datetime
import requests

from DMR.utils import replace_keywords, ToolsList, VideoInfo
from DMR.LiveAPI.bilibili import bilibili as BiliLiveAPI


class biliuprs():

    def __init__(self,
                 cookies: str = None,
                 account: str = None,
                 task_upload_lock: bool = True,
                 debug=False,
                 biliup: str = None,
                 **kwargs,
                 ) -> None:
        self.biliup = biliup if biliup else ToolsList.get('biliup')

        if not (cookies or account):
            raise ValueError('cookies or account must be set.')

        if cookies is None:
            self.account = account
            self.cookies = f'.login_info/{account}.json'
        else:
            self.account = os.path.basename(cookies).split('.')[0]
            self.cookies = cookies
        os.makedirs(os.path.dirname(self.cookies), exist_ok=True)

        self.task_upload_lock = task_upload_lock
        self.debug = debug

        self.base_args = [self.biliup, '-u', self.cookies]
        self.task_info = {}
        self._upload_lock = threading.Lock()
        self._upload_procs = {}
        self.logger = logging.getLogger(__name__)
        self.stoped = False

        # 窗口控制
        self._new_work_window_triggered = None
        self._window_lock = threading.Lock()

        if not self.islogin():
            self.login()

    def __del__(self):
        self.stop()

    def call_biliuprs(self, video, bvid=None, copyright=1, cover='', desc='', dtime=0, dynamic='',
                      line=None, limit=3, no_reprint=1, source='', tag='', tid=65, title='',
                      extra_args=None, timeout=None, logfile=None, **kwargs):
        if bvid:
            upload_args = self.base_args + ['append', '--vid', bvid]
        else:
            upload_args = self.base_args + ['upload']

        dtime = dtime + int(time.time()) if dtime else 0
        upload_args += [
            '--copyright', copyright,
            '--cover', cover,
            '--desc', desc,
            '--dtime', dtime,
            '--dynamic', dynamic,
            '--limit', limit,
            '--no-reprint', no_reprint,
            '--source', source,
            '--tag', tag,
            '--tid', tid,
            '--title', title,
        ]
        if line:
            upload_args += ['--line', line]
        if extra_args:
            upload_args += extra_args

        if isinstance(video, str):
            upload_args += [video]
        elif isinstance(video, list):
            upload_args += video

        upload_args = [str(x) for x in upload_args]
        self.logger.debug(f'biliuprs: {upload_args}')

        if not logfile:
            logfile = sys.stdout

        if self.debug:
            upload_proc = subprocess.Popen(upload_args, stdin=subprocess.PIPE, stdout=sys.stdout,
                                           stderr=subprocess.STDOUT, bufsize=10 ** 8)
        else:
            upload_proc = subprocess.Popen(upload_args, stdin=subprocess.PIPE, stdout=logfile,
                                           stderr=subprocess.STDOUT, bufsize=10 ** 8)

        try:
            self._upload_procs[upload_proc.pid] = upload_proc
            if timeout:
                upload_proc.wait(timeout=timeout)
            else:
                upload_proc.wait()
        except subprocess.TimeoutExpired:
            self.logger.warning(f'视频{video}上传超时，取消此次上传.')
        finally:
            upload_proc.kill()
            self._upload_procs.pop(upload_proc.pid, None)

        return logfile, upload_args

    def islogin(self):
        renew_args = self.base_args + ['renew']
        proc = subprocess.Popen(renew_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, bufsize=10 ** 8)
        out = proc.stdout.read().decode('utf-8')
        return 'error' not in out.lower()

    def login(self):
        login_args = self.base_args + ['login']
        for _ in range(5):
            self.logger.info(f'正在登录名称为 {self.account} 的账户:')
            proc = subprocess.Popen(login_args)
            proc.wait(timeout=120)
            if self.islogin():
                self.logger.info(f'将 {self.account} 的登录信息保存到 {self.cookies}.')
                break
        else:
            self.logger.error(f'{self.account} 登录失败!.')

    def upload_once(self, video, bvid=None, **config):
        with tempfile.TemporaryFile(dir='.temp') as logfile:
            self.call_biliuprs(video=video, bvid=bvid, logfile=logfile, **config)
            if self.debug:
                return True, ''

            out_bvid = None
            log = ''
            logfile.seek(0)
            for line in logfile.readlines():
                line = line.decode('utf-8', errors='ignore').strip()
                log += line + '\n'
                if '\"bvid\"' in line:
                    res = re.search(r'(BV[0-9A-Za-z]{10})', line)
                    if res:  out_bvid = res[0]

        if out_bvid:
            return True, out_bvid
        else:
            return False, log

    def format_config(self, config, video_info=None, replace_invalid=False):
        config = config.copy()
        if config.get('title'):
            config['title'] = replace_keywords(config['title'], video_info, replace_invalid=replace_invalid)
            if len(config['title']) > 80:
                config['title'] = config['title'][:80]
                self.logger.warning(f'视频标题超过80字符，已自动截取为: {config["title"]}.')
        if config.get('desc'):
            config['desc'] = replace_keywords(config['desc'], video_info, replace_invalid=replace_invalid)
        if config.get('dynamic'):
            config['dynamic'] = replace_keywords(config['dynamic'], video_info, replace_invalid=replace_invalid)
        if config.get('tag'):
            if isinstance(config['tag'], list):
                config['tag'] = ','.join(config['tag'])
            config['tag'] = replace_keywords(config['tag'], video_info, replace_invalid=replace_invalid)
        if config.get('source'):
            config['source'] = replace_keywords(config['source'], video_info, replace_invalid=replace_invalid)
        if config.get('cover'):
            config['cover'] = replace_keywords(config['cover'], video_info, replace_invalid=replace_invalid)
            if config['cover'].startswith('http'):
                try:
                    resp = requests.get(config['cover'], headers={'User-Agent': 'Mozilla/5.0'}, timeout=5.0)
                    resp.raise_for_status()
                    cover_filename = f'.temp/biliuprs_cover_{int(time.time()) + 86400}.png'
                    with open(cover_filename, 'wb') as f:
                        f.write(resp.content)
                    config['cover'] = cover_filename
                except Exception as e:
                    self.logger.error(f'视频 {config["title"]} 封面图片下载失败: {e}, 跳过设置.')
                    config['cover'] = ''
        return config

    # --------------- 新增/修改的辅助方法 ---------------
    def _get_live_title(self, room_id):
        """复用项目 B 站 API 获取直播间当前标题"""
        try:
            live_api = BiliLiveAPI(room_id)
            title, _, _, _ = live_api.get_info()
            self.logger.debug(f'获取到直播间 {room_id} 标题: {title}')
            return title
        except Exception as e:
            self.logger.error(f'获取直播间 {room_id} 标题失败: {e}')
            return None

    def _update_title_for_append(self, config, video_info, bvid):
        """追加稿件时，用直播间最新标题更新 config"""
        if bvid is None:
            return config

        try:
            room_id = video_info.streamer.url.rstrip('/').split('/')[-1]
            if not room_id.isdigit():
                self.logger.debug(f'无法提取房间号: {video_info.streamer.url}')
                return config
        except Exception as e:
            self.logger.debug(f'解析房间号失败: {e}')
            return config

        new_title = self._get_live_title(room_id)
        if not new_title:
            return config

        # 临时替换 title，重新格式化 config（保证其他模板变量不变）
        original_title = video_info.title
        video_info.title = new_title
        new_config = self.format_config(config.copy(), video_info)
        video_info.title = original_title
        return new_config

    def _should_create_new_work(self):
        now = datetime.datetime.now()
        current_hour = now.hour
        windows = [(2, 3), (12, 13), (18, 19)]

        window_start = None
        for start, end in windows:
            if start <= current_hour < end:
                window_start = start
                break

        if window_start is None:
            return False

        with self._window_lock:
            if self._new_work_window_triggered == window_start:
                return False
        return True

    def _mark_window_triggered(self):
        now = datetime.datetime.now()
        current_hour = now.hour
        windows = [(2, 3), (12, 13), (18, 19)]
        for start, end in windows:
            if start <= current_hour < end:
                with self._window_lock:
                    self._new_work_window_triggered = start
                self.logger.debug(f"已标记 {start}-{end} 时间窗口新建完成。")
                break

    def _upload_with_retry(self, video_files, bvid, config):
        status, result = self.upload_once(video=video_files, bvid=bvid, **config)
        if status:
            return True, result

        if bvid and '已锁定' in result:
            self.logger.warning(f'稿件 {bvid} 已锁定（审核/删除等），将重新上传为新稿件。')
            status, new_bvid = self.upload_once(video=video_files, bvid=None, **config)
            if status:
                self.logger.info(f'新稿件已创建：{new_bvid}')
                return True, new_bvid
            else:
                self.logger.error('重新上传新稿件仍然失败。')
                return False, new_bvid
        else:
            return False, result

    # ------------------------------------------------

    def upload(self, files: list, **kwargs):
        if not isinstance(files, list):
            files = [files]
        config = self.format_config(kwargs, files[0])
        config.pop('bvid', None)

        video_files = [f.path for f in files]

        external_bvid = kwargs.get('bvid', None)
        force_new = self._should_create_new_work()
        if force_new:
            self.logger.info(f"当前时间 {datetime.datetime.now().strftime('%H:%M')} 处于新稿件创建时段，将开始一个新稿件。")
            final_bvid = None
        else:
            final_bvid = external_bvid if external_bvid is not None else self.task_info.get('bvid')

        status, bvid = False, ''

        if self.task_upload_lock:  # 串行
            with self._upload_lock:
                config = self._update_title_for_append(config, files[0], final_bvid)
                status, bvid = self._upload_with_retry(video_files, final_bvid, config)
                if status:
                    self.task_info['bvid'] = bvid
                    if force_new:
                        self._mark_window_triggered()
        else:  # 并行
            if self.task_info.get('bvid') is None:
                self._upload_lock.acquire()
                lock_released = False
                try:
                    if self.task_info.get('bvid'):
                        self._upload_lock.release()
                        lock_released = True
                        bvid_to_use = self.task_info['bvid']
                        force_new = False
                    else:
                        bvid_to_use = final_bvid
                    config = self._update_title_for_append(config, files[0], bvid_to_use)
                    status, bvid = self._upload_with_retry(video_files, bvid_to_use, config)
                    if status:
                        self.task_info['bvid'] = bvid
                        if force_new and bvid_to_use is None:
                            self._mark_window_triggered()
                finally:
                    if not lock_released:
                        self._upload_lock.release()
            else:
                if final_bvid is None and self.task_info.get('bvid') is not None:
                    bvid_to_use = None
                    self.logger.debug("时间窗口强制新建稿件，将忽略已存在的 bvid。")
                else:
                    bvid_to_use = self.task_info.get('bvid')
                config = self._update_title_for_append(config, files[0], bvid_to_use)
                status, bvid = self._upload_with_retry(video_files, bvid_to_use, config)
                if status:
                    self.task_info['bvid'] = bvid
                    if force_new and bvid_to_use is None:
                        self._mark_window_triggered()

        return status, bvid

    def end_upload(self):
        self.task_info = {}
        self.logger.debug('realtime upload end.')

    def stop(self):
        self.stoped = True
        try:
            if self._upload_procs:
                self.logger.warning('上传提前终止，可能需要重新上传.')
            for proc in list(self._upload_procs.values()):
                proc.kill()
                out, _ = proc.communicate(timeout=2.0)
                self.logger.debug(out.decode('utf-8'))
        except Exception as e:
            self.logger.debug(e)