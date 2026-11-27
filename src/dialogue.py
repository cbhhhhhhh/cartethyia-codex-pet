"""Persona constraints, the shared picture gallery, and explicit references to performed actions."""
from functools import lru_cache
import json
import subprocess
from pathlib import Path
import random
import re

HERE = Path(__file__).resolve().parent
WEATHER = re.compile(r"天气|气象|气温|温度|湿度|降水|体感|摄氏|华氏|[℃℉]|[晴阴雨雪雾霜雷雹]|刮风|凉风|寒风|微风|风向|风速|风和日丽|风很大|多云|闷热|寒潮|酷热|转凉|阳光|日晒|humidity|weather|sunny|rain(?:y|ing)?\b|snow(?:y|ing)?\b|cloudy|forecast|temperature", re.I)
PLACES = ("北京 上海 天津 重庆 成都 杭州 苏州 宁波 广州 深圳 香港 澳门 台北 东京 大阪 京都 上海市 "
          "西安 武汉 南京 青岛 大连 沈阳 西宁 兰州 拉萨 乌鲁木齐 哈尔滨 石家庄 郑州 长沙 南昌 合肥 "
          "太原 济南 海口 福州 厦门 南宁 昆明 贵阳 银川 呼和浩特 长春 桂林 大理 丽江 敦煌 洛阳 "
          "中国 美国 日本 韩国 英国 法国 德国 俄罗斯 澳大利亚 加拿大 伦敦 巴黎 纽约 加州 硅谷 西雅图 "
          "长江 黄河 长城 西湖 泰山 珠峰 印度 意大利 威尼斯 罗马 柏林 莫斯科 新加坡 台湾 四川 云南 "
          "浙江 广东 江苏 山东 海南 新疆 湖北 湖南 陕西 广西 贵州 甘肃 青海 福建 吉林 河南 河北 山西 "
          "黑龙江 安徽 西藏 内蒙古 辽宁 宁夏 江西 索拉里斯 黎那汐塔 今州 拉古那 乘霄山 黑海岸 七丘 "
          "瑝珑 黎那汐塔地区 翡萨烈 维奥里亚 霜落港 狄萨莱 坎特蕾拉故乡 穗波 虹镇 港市归墟 稷廷 "
          "蒙德 璃月 稻妻 枫丹 须弥 Beijing Shanghai Paris Tokyo London Wuhan Rinascita Ragunna Septimont").split()
PLACE = re.compile("|".join(map(re.escape, PLACES)) +
                   r"|[\u3400-\u9fff]{2,8}(?:自治[区州县]|特别行政区|省会|[市县镇]区|市中心|县城|港口|山脉|群岛)|(?:来到|坐标在|位于|去过|来自|身处|走在)[\u3400-\u9fff]{2,8}(?:市|省|县|区|镇|村|城|岛|港|洲|山|河|湖)", re.I)
NEG = r"(?:不要|不许|不得|不准|不能|不可|禁止|切勿|避免|绝不|不再|不提|别|禁谈|禁用|不出现|不包含|never|avoid|do not|don't)"
def forbids(persona, topic):
    return any(re.search(NEG, clause, re.I) and re.search(topic, clause, re.I)
               for clause in re.split(r"[。！？；\n;!]", persona))


@lru_cache(maxsize=192)
def local_place_name(sentence):
    tagger = HERE.parent / "MacOS/pet-place"
    if tagger.is_file():
        try:
            result = subprocess.run([str(tagger)], input=sentence[:6000], text=True,
                                    capture_output=True, timeout=3)
            return result.stdout.strip() == "1"
        except (OSError, subprocess.TimeoutExpired):
            pass
    return False


class Rules:
    def __init__(self, cfg):
        persona = cfg.get("persona") or ""
        self.weather = bool(cfg.get("avoidWeather") or forbids(persona, r"天气|气象|气温|weather"))
        self.places = bool(cfg.get("avoidPlaces") or forbids(persona, r"地名|城市名|地点|地理位置|现实城市|place names?|locations?"))
        self.extra = [x.strip() for x in re.split(r"[、，,\n]", cfg.get("blockedWords") or "") if x.strip()]
        self.strict = bool(self.weather or self.places or self.extra)

    def allows(self, text):
        return not ((self.weather and WEATHER.search(text)) or
                    (self.places and (PLACE.search(text) or local_place_name(text))) or
                    any(x.casefold() in text.casefold() for x in self.extra))

    def instruction(self):
        parts = []
        if self.weather:
            parts.append("所有回复禁谈天气、气候和温度，即使用户问起也温和换一个话题。")
        if self.places:
            parts.append("不要说出真实或虚构的地名，绕开地点话题。")
        if self.extra:
            parts.append("不用以下词语：" + "、".join(self.extra))
        return "".join(parts)

    def safe_line(self):
        return next((x for x in ("我在。想让我陪你做点什么？", "我听着呢。", "嗯。", "…") if self.allows(x)), "")


def gallery(folder, pack="cartethyia"):
    pictures = {}
    if pack == "cartethyia":
        for item in json.loads((HERE / "web/gallery.json").read_text()):
            file = HERE / "web/portraits" / (item["id"] + ".png")
            if file.is_file():
                pictures[item["id"]] = dict(item, file=str(file))
    for path in sorted((folder / "stickers").glob("*")):
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in (".png", ".jpeg", ".jpg"):
            key = "custom-" + path.name
            pictures[key] = dict(id=key, title=path.stem, description=path.stem, mood="custom", file=str(path))
    return pictures


def gallery_pick(pictures, user, emotion, previous, forced, enabled, whisper, rules, recent=None):
    if forced:
        return pictures.get(forced)
    asks = bool(re.search(r"(?:发|看|来|给|换).{0,6}(?:表情|插画|配图|张图|一张)|换一张", user))
    if not enabled and not asks:
        return None
    expressive = emotion in ("happy", "sad") and bool(re.search(r"庆祝|抱抱|安慰|开心|太好|好难过", user))
    if not (asks or expressive or whisper and random.random() < .15):
        return None
    if not asks and (previous if recent is None else recent):
        return None
    pool = [p for p in pictures.values() if rules.allows(p["description"]) and p["id"] != previous]
    match = [p for p in pool if p["mood"] == emotion or p["title"] in user]
    return random.choice(match or pool) if pool else None


def action_request(text, catalogue, last=""):
    if last in catalogue and re.search(r"再来一次|再[表演播做]一次|再来一遍|刚才那个再|刚刚那个再", text):
        return last
    if text.strip(" 。，！!?？") in catalogue:
        return text.strip(" 。，！!?？")
    if "换个动作" in text:
        pool = [k for k in catalogue if k != last]
        return random.choice(pool) if pool else ""
    aliases = {"行礼": "提裙行骑士礼", "行个礼": "提裙行骑士礼", "鞠躬": "提裙行骑士礼", "写字": "写下旅途一笔",
               "拆礼物": "拆开丝带礼物", "吹笛": "吹响旅人的短笛", "拉小提琴": "拉一段小提琴", "跳支舞": "城堡里的圆舞曲"}
    for term, title in aliases.items():
        if term in text and title in catalogue:
            return title
    if not re.search(r"表演|给我|演示|来个|来一|想看|能不能|跳|请你|再来|做个|做一|换个动作", text):
        return ""
    def score(name):
        if name in text:
            return 100 + len(name)
        return sum(1 for i in range(len(name)-1) if name[i:i+2] in text)
    ranked = sorted(((score(name), name) for name in catalogue), reverse=True)
    return ranked[0][1] if ranked and ranked[0][0] >= 2 else ""

# Lines accompany a specific beat and share the profile's speech restrictions.
CUES = {
    "提裙行骑士礼": ("向你致意。", "请收下小骑士的敬意。"),
    "写下旅途一笔": ("写好了，这一页留给你。", "等我把这一笔收好。"),
    "拆开丝带礼物": ("拉这头就能解开……给你看！", "我猜不出来，一起拆吧。"),
    "挥笔写下福字": ("最后一笔，该收锋了。", "墨还没干，先放在这里。"),
    "拉一段小提琴": ("这句旋律，你听到了吗？", "下一小节，送给你。"),
    "蹲下来摸猫": ("它把下巴递过来了。", "嘘，让它再靠一会儿。"),
    "偷吃一块饼干": ("唔……你也要一块吗？", "被你发现啦。"),
    "在棋盘上落子": ("这一步，轮到你了。", "我想好啦，就放这里。"),
    "被小兔子围住": ("慢一点，一个一个来。", "它的耳朵蹭到我啦。"),
    "掌心绽开一朵花": ("伸出手，送给你。", "你看，它开了。"),
    "轻轻别过脸": ("……我听见了。", "再喊我一次嘛。"),
    "见到你开心一跳": ("你来啦！", "我一直给你留着位置。"),
    "陪小车跑一段": ("跟上啦，小车！", "一、二，出发。"),
    "帮你敲几行代码": ("敲完这行，我们一起看看。", "最后一个括号也合上了。"),
    "举高小手问好": ("在这边！", "见到你真好。"),
    "遮住一个哈欠": ("陪我伸个懒腰吧。", "我只眯了一小下。"),
    "让蝴蝶落在花上": ("轻轻的……它停住了。", "先别动，它过来啦。"),
    "翻出红心纸牌": ("记住这张牌哦。", "猜猜我的手心里有什么？"),
    "切开清凉西瓜": ("这块尖尖的，留给你。", "一人一半，刚刚好。"),
    "揉揉眼睛伸懒腰": ("嗯，我醒啦。", "再陪你一会儿。"),
}


def cue_line(name, rules):
    choices = [line for line in CUES.get(name, ()) if rules.allows(line)]
    return random.choice(choices) if choices else ""
