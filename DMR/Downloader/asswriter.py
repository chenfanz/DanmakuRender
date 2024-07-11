from datetime import datetime
import threading
from DMR.danmaku import SimpleDanmaku
from DMR.utils import *

__all__ = ['AssWriter']

class AssWriter():
    """
    ASS弹幕写入器，定义了ASS弹幕格式和信息，用于流式处理弹幕
    """
    def __init__(self,
                 description:str,
                 width:int,
                 height:int,
                 dst:int,
                 dmrate:float,
                 font:str,
                 fontsize:int,
                 margin_h:int,
                 margin_w:int,
                 dmduration:float,
                 opacity:float,
                 auto_fontsize:bool,
                 outlinecolor:str,
                 outlinesize:int,
                 **kwargs) -> None:
        self.description = description
        self.height = height
        self.width = width
        self.dmrate = dmrate
        if auto_fontsize:
            self.fontsize = int(height / 1080 * fontsize)
        else:
            self.fontsize = int(fontsize)
        self.font = font

        self.margin_h = margin_h if margin_h > 1 else margin_h * self.height
        self.margin_w = margin_w if margin_w > 1 else margin_w * self.width
        self.dst = dst
        self.dmduration = dmduration
        self.opacity = hex(255-int(opacity*255))[2:].zfill(2)
        self.outlinecolor = str(outlinecolor).zfill(6)
        self.outlinesize = outlinesize
        self.kwargs = kwargs

        self._lock = threading.Lock()
        self._super_chat_tails = []  # 初始化 _super_chat_tails 属性
        self._ntracks = int(((self.height - self.dst) * self.dmrate) / (self.fontsize + self.margin_h))

        self.meta_info = [
            '[Script Info]',
            f'Title: {self.description}',
            'ScriptType: v4.00+',
            'Collisions: Normal',
            f'PlayResX: {self.width}',
            f'PlayResY: {self.height}',
            'Timer: 100.0000',
            '',
            '[V4+ Styles]',
            'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
            f'Style: R2L,{self.font},{self.fontsize},&H{self.opacity}FFFFFF,&H{self.opacity}000000,&H{self.opacity}{self.outlinecolor},&H4F0000FF,-1,0,0,0,100,100,0,0,1,{self.outlinesize},0,1,0,0,0,0',
            f'Style: message_box,Microsoft YaHei,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H1E6A5149,1,0,0,0,100.00,100.00,0.00,0.00,1,1,0,7,0,0,0,1',
            '',
            '[Events]',
            'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
        ]

    def _get_length(self, string:str):
        length = 0
        for s in string:
            if len(s.encode('utf-8')) == 1:
                length += 0.5*self.fontsize
            else:
                length += self.fontsize
        return int(length)

    def open(self, filename):
        with self._lock, open(filename,'w',encoding='utf-8') as f:
            self._filename = filename
            self._track_tails = [None for _ in range(self._ntracks)]
            for info in self.meta_info:
                f.write(info+'\n')
    
    def add(self, danmu:SimpleDanmaku, calc_collision=True):
        """
        添加弹幕到ASS文件 
        danmu: 待添加弹幕
        calc_collision: 是否计算冲突，冲突的弹幕将会被自动忽略
        """
        tid, max_dist = 0, -1e5
        
        # 计算给出弹幕到指定弹幕的距离
        def tail_dist(tail_dm:SimpleDanmaku, tic:float):
            if not tail_dm:
                return 1e5
            dm_length = self._get_length(tail_dm.content)
            dist = (tic - tail_dm.time) * (dm_length + self.width) / self.dmduration - dm_length 
            return dist
        
        for i, tail_dm in enumerate(self._track_tails):
            dist = tail_dist(tail_dm, danmu.time)
            if dist > 0.2 * self.width and dist > self.margin_w:
                tid = i
                max_dist = dist
                break
            if dist > max_dist:
                max_dist = dist
                tid = i
        
        if calc_collision and max_dist < self.margin_w:
            return False
        
        dm_length = self._get_length(danmu.content)
        x0 = self.width
        x1 = -dm_length
        y = self.fontsize + (self.fontsize + self.margin_h) * tid

        t0 = danmu.time
        t1 = t0 + self.dmduration

        t0 = '%02d:%02d:%05.2f'%sec2hms(t0)
        t1 = '%02d:%02d:%05.2f'%sec2hms(t1)
        
        # set ass Dialogue
        dm_info = f'Dialogue: 0,{t0},{t1},R2L,,0,0,0,,'
        dm_info += '{\move(%d,%d,%d,%d)}'%(x0, y + self.dst, x1, y + self.dst)
        dm_info += '{\\alpha&H%s\\1c%s&}'%(self.opacity, RGB2BGR(danmu.color))
        content = danmu.content.replace('\n',' ').replace('\r',' ')
        dm_info += content

        with self._lock, open(self._filename, 'a', encoding='utf-8') as f:
            f.write(dm_info + '\n')
        
        self._track_tails[tid] = danmu
        return True

    def add_super_chat(self, super_chat: SimpleDanmaku):
        with self._lock:
            if not self._filename:
                raise RuntimeError("ASS file is not open.")

            # 格式化超级弹幕内容
            content_lines = []
            for i in range(0, len(super_chat.content), 15):
                content_lines.append(super_chat.content[i:i + 15])
            formatted_content = '\\N'.join(content_lines)

            dm_length = self._get_length(formatted_content)
            x0 = -100  # 初始X位置，负数表示从屏幕左侧外开始移动
            x1 = 0  # 最终X位置
            y = 189

            t0 = super_chat.time
            t1 = t0 + 0.25  # Super Chat 移动时间

            t0_move = '%02d:%02d:%05.2f' % sec2hms(t0)
            t1_move = '%02d:%02d:%05.2f' % sec2hms(t1)

            t0_display = t1_move
            t1_display = '%02d:%02d:%05.2f' % sec2hms(t1 + 20)  # Super Chat 持续时间固定为20秒

            # 构建 ASS 格式的弹幕信息
            dm_info = (
                f'Dialogue: 0,{t0_move},{t1_move},message_box,,0000,0000,0000,,'
                f'{{\\move({x0},{y},{x1},{y})\\c&HE5E5FF\\shad0\\p1}}m 0 12 b 0 6 6 0 12 0 l 238 0 b 244 0 250 6 250 12 l 250 51 l 0 51\n'
                f'Dialogue: 0,{t0_move},{t1_move},message_box,,0000,0000,0000,,'
                f'{{\\move({x0},{y + 51},{x1},{y + 51})\\shad0\\p1\\c&H8C8CF7}}m 0 0 l 250 0 l 250 44 b 250 50 244 56 238 56 l 12 56b 6 56 0 50 0 44\n'
                f'Dialogue: 1,{t0_move},{t1_move},message_box,,0000,0000,0000,,'
                f'{{\\move({x0 + 6},{y + 4},{x1 + 6},{y + 4})\\c&H0F0F75\\fs25\\b1\\q2}}{super_chat.uname}\n'
                f'Dialogue: 1,{t0_move},{t1_move},message_box,,0000,0000,0000,,'
                f'{{\\move({x0 + 6},{y + 29},{x1 + 6},{y + 29})\\c&H313131\\fs20\\q2}}SuperChat CNY {super_chat.price}\n'
                f'Dialogue: 1,{t0_move},{t1_move},message_box,,0000,0000,0000,,'
                f'{{\\move({x0 + 6},{y + 51},{x1 + 6},{y + 51})\\c&HFFFFFF\\q2}}{formatted_content}\n'
                f'Dialogue: 0,{t0_display},{t1_display},message_box,,0000,0000,0000,,'
                f'{{\\pos({x1},{y})\\clip(m 0 212 b 0 206 6 200 12 200 l 238 200 b 244 200 250 206 250 212 l 250 300 l 0 300)\\c&HE5E5FF\\shad0\\p1}}m 0 12 b 0 6 6 0 12 0 l 238 0 b 244 0 250 6 250 12 l 250 51 l 0 51\n'
                f'Dialogue: 0,{t0_display},{t1_display},message_box,,0000,0000,0000,,'
                f'{{\\pos({x1},{y + 51})\\clip(m 0 212 b 0 206 6 200 12 200 l 238 200 b 244 200 250 206 250 212 l 250 300 l 0 300)\\shad0\\p1\\c&H8C8CF7}}m 0 0 l 250 0 l 250 44 b 250 50 244 56 238 56 l 12 56b 6 56 0 50 0 44\n'
                f'Dialogue: 1,{t0_display},{t1_display},message_box,,0000,0000,0000,,'
                f'{{\\pos({x1 + 6},{y + 4})\\clip(m 0 212 b 0 206 6 200 12 200 l 238 200 b 244 200 250 206 250 212 l 250 300 l 0 300)\\c&H0F0F75\\fs25\\b1\\q2}}{super_chat.uname}\n'
                f'Dialogue: 1,{t0_display},{t1_display},message_box,,0000,0000,0000,,'
                f'{{\\pos({x1 + 6},{y + 29})\\clip(m 0 212 b 0 206 6 200 12 200 l 238 200 b 244 200 250 206 250 212 l 250 300 l 0 300)\\c&H313131\\fs20\\q2}}SuperChat CNY {super_chat.price}\n'
                f'Dialogue: 1,{t0_display},{t1_display},message_box,,0000,0000,0000,,'
                f'{{\\pos({x1 + 6},{y + 51})\\clip(m 0 212 b 0 206 6 200 12 200 l 238 200 b 244 200 250 206 250 212 l 250 300 l 0 300)\\c&HFFFFFF\\q2}}{formatted_content}\n'
            )

            with open(self._filename, 'a', encoding='utf-8') as f:
                f.write(dm_info)

            self._super_chat_tails.append(super_chat)

    def close(self):
        del self._filename
        del self._track_tails
