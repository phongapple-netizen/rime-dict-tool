"""Rime 词库工具的文件读写逻辑。界面在 rime_dict_tool.pyw。"""
import datetime
import os
import shutil
import winreg
from collections import defaultdict
from dataclasses import dataclass

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
PHRASE_FILE = "custom_phrase.txt"
PERSONAL_FILE = "wubi86_personal.dict.yaml"
BASE_FILE = "wubi86.dict.yaml"
PREDICT_FILE = "predict_user.tsv"
PREDICT_HEADER = (
    "# 用户自定义联想，由 Rime 词库工具维护\n"
    "# 格式：前词<Tab>联想词；前词<Tab>!联想词 表示隐藏词库里的这个词\n"
)
DEFAULT_PHRASE_WEIGHT = 1000000
DEFAULT_PERSONAL_WEIGHT = 900000


def rime_user_dir():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Rime\Weasel") as key:
            value = winreg.QueryValueEx(key, "RimeUserDir")[0]
            if value:
                return value
    except OSError:
        pass
    return os.path.join(os.environ["APPDATA"], "Rime")


def deployer_path():
    for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Rime\Weasel", 0,
                                winreg.KEY_READ | view) as key:
                return os.path.join(winreg.QueryValueEx(key, "WeaselRoot")[0], "WeaselDeployer.exe")
        except OSError:
            continue
    raise FileNotFoundError("找不到小狼毫的安装位置")


@dataclass
class Entry:
    text: str
    code: str
    weight: float
    source: str  # phrase / personal / base / learned


SOURCE_LABELS = {"phrase": "自定义短语", "personal": "个人词典", "base": "基础码表（只读）",
                 "learned": "已学习（只读）"}


class Store:
    def __init__(self, root=None, backup_root=None, tsv_path=None):
        self.root = root or rime_user_dir()
        self.backup_root = backup_root or os.path.join(TOOL_DIR, "backups")
        self.tsv_path = tsv_path or os.path.join(TOOL_DIR, "data", "predict-zhs.tsv")
        self.base = []
        self.char_code = {}
        self.db_predict = defaultdict(list)
        self._load_static()

    # ---------- 读写基础 ----------
    def _path(self, name):
        return os.path.join(self.root, name)

    def _read(self, name):
        path = self._path(name)
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()

    def _write(self, name, text):
        path = self._path(name)
        if os.path.exists(path):
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            folder = os.path.join(self.backup_root, stamp)
            os.makedirs(folder, exist_ok=True)
            shutil.copy2(path, os.path.join(folder, name))
        tmp = path + ".rimetool.tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)

    @staticmethod
    def _eol(text):
        return "\r\n" if "\r\n" in text else "\n"

    @staticmethod
    def _append_line(text, line):
        eol = Store._eol(text)
        if text and not text.endswith("\n"):
            text += eol
        return text + line + eol

    @staticmethod
    def _clean(value, name):
        value = value.strip()
        if not value:
            raise ValueError(f"{name}不能为空")
        if "\t" in value or "\n" in value or "\r" in value:
            raise ValueError(f"{name}不能包含 Tab 或换行")
        return value

    @staticmethod
    def _clean_code(code):
        code = code.strip().lower()
        if not code or not code.isascii() or not code.isalpha():
            raise ValueError("编码只能是英文字母")
        return code

    @staticmethod
    def _body_start(lines):
        for i, line in enumerate(lines):
            if line.rstrip("\r\n") == "...":
                return i + 1
        return 0

    def _load_static(self):
        best = {}
        lines = self._read(BASE_FILE).splitlines()
        for line in lines[self._body_start(lines):]:
            if not line or line.startswith("#"):
                continue
            p = line.split("\t")
            if len(p) < 2:
                continue
            weight = float(p[2]) if len(p) > 2 and p[2] else 0
            self.base.append(Entry(p[0], p[1], weight, "base"))
            stem = p[3] if len(p) > 3 else ""
            if len(p[0]) == 1:
                candidate = max(p[1], stem, key=len)
                if len(candidate) > len(best.get(p[0], "")):
                    best[p[0]] = candidate
        self.char_code = best
        if os.path.exists(self.tsv_path):
            with open(self.tsv_path, encoding="utf-8") as f:
                for line in f:
                    p = line.rstrip("\r\n").split("\t")
                    if len(p) >= 2 and not line.startswith("#"):
                        self.db_predict[p[0]].append(p[1])

    # ---------- 编码 ----------
    def auto_code(self, word):
        """按个人词典的 86 五笔规则算编码；含未知字时返回空字符串。"""
        codes = [self.char_code.get(ch) for ch in word]
        if not codes or not all(codes):
            return ""
        if len(codes) == 1:
            return codes[0]
        if len(codes) == 2:
            return codes[0][:2] + codes[1][:2]
        if len(codes) == 3:
            return codes[0][0] + codes[1][0] + codes[2][:2]
        return codes[0][0] + codes[1][0] + codes[2][0] + codes[-1][0]

    # ---------- 读取条目 ----------
    def phrases(self):
        result = []
        for line in self._read(PHRASE_FILE).splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            p = line.split("\t")
            if len(p) >= 2:
                result.append(Entry(p[0], p[1], float(p[2]) if len(p) > 2 and p[2] else 0, "phrase"))
        return result

    def personal(self):
        result = []
        lines = self._read(PERSONAL_FILE).splitlines()
        for line in lines[self._body_start(lines):]:
            if not line.strip() or line.startswith("#"):
                continue
            p = line.split("\t")
            result.append(Entry(p[0], self.auto_code(p[0]),
                                float(p[1]) if len(p) > 1 and p[1] else 0, "personal"))
        return result

    def learned(self):
        result = []
        folder = self._path("sync")
        install = self._read("installation.yaml")
        if not os.path.isdir(folder):
            return result
        for name in os.listdir(folder):
            if name not in install:
                continue
            path = os.path.join(folder, name, "wubi86_personal.userdb.txt")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("#"):
                        continue
                    p = line.rstrip("\r\n").split("\t")
                    if len(p) >= 3:
                        count = 0.0
                        for field in p[2].split():
                            if field.startswith("c="):
                                try:
                                    count = float(field[2:])
                                except ValueError:
                                    pass
                        result.append(Entry(p[1], p[0].strip().replace(" ", ""), count, "learned"))
        return result

    def all_entries(self):
        return self.phrases() + self.personal() + self.learned() + self.base

    def search(self, query, limit=500):
        query = query.strip()
        if not query:
            return []
        order = {"phrase": 0, "personal": 1, "learned": 2, "base": 3}
        code_query = query.isascii() and query.isalpha()
        q = query.lower()
        hits = []
        for e in self.all_entries():
            if code_query:
                if e.code == q:
                    rank = 0
                elif e.code.startswith(q):
                    rank = 1
                else:
                    continue
            else:
                if e.text == query:
                    rank = 0
                elif query in e.text:
                    rank = 1
                else:
                    continue
            hits.append((rank, len(e.code) if code_query else len(e.text),
                         order[e.source], -e.weight, e))
        hits.sort(key=lambda h: h[:4])
        return [h[4] for h in hits[:limit]]

    def same_code(self, code, exclude_text=None):
        return [e for e in self.all_entries() if e.code == code and e.text != exclude_text]

    # ---------- 自定义短语 ----------
    def upsert_phrase(self, text, code, weight=DEFAULT_PHRASE_WEIGHT, old_text=None, old_code=None):
        text = self._clean(text, "词语")
        code = self._clean_code(code)
        weight = int(weight)
        if weight < 0:
            raise ValueError("权重不能小于 0")
        old_text = old_text if old_text is not None else text
        old_code = old_code if old_code is not None else code
        raw = self._read(PHRASE_FILE)
        eol = self._eol(raw)
        lines = raw.split(eol) if raw else []
        new_line = f"{text}\t{code}\t{weight}"
        for i, line in enumerate(lines):
            p = line.split("\t")
            if not line.startswith("#") and len(p) >= 2 and p[0] == old_text and p[1] == old_code:
                lines[i] = new_line
                self._write(PHRASE_FILE, eol.join(lines))
                return
        self._write(PHRASE_FILE, self._append_line(raw, new_line))

    def delete_phrase(self, text, code):
        raw = self._read(PHRASE_FILE)
        eol = self._eol(raw)
        lines = raw.split(eol)
        kept = [ln for ln in lines
                if ln.startswith("#") or ln.split("\t")[:2] != [text, code]]
        if len(kept) == len(lines):
            raise ValueError("文件里已没有这个词条")
        self._write(PHRASE_FILE, eol.join(kept))

    def pin_to_top(self, text, code):
        """让词排到该编码首位：写入自定义短语，权重取同码短语最大值加 1。"""
        same = [e.weight for e in self.phrases() if e.code == code and e.text != text]
        self.upsert_phrase(text, code, int(max(same + [DEFAULT_PHRASE_WEIGHT - 1])) + 1)

    # ---------- 个人词典 ----------
    def upsert_personal(self, text, weight=DEFAULT_PERSONAL_WEIGHT, old_text=None):
        text = self._clean(text, "词语")
        weight = int(weight)
        if weight < 0:
            raise ValueError("权重不能小于 0")
        if not self.auto_code(text):
            raise ValueError("词里有基础码表找不到的字，无法自动生成编码，请填写自定义编码")
        old_text = old_text if old_text is not None else text
        raw = self._read(PERSONAL_FILE)
        eol = self._eol(raw)
        lines = raw.split(eol)
        start = self._body_start(lines)
        for i in range(start, len(lines)):
            line = lines[i]
            if line and not line.startswith("#") and line.split("\t")[0] == old_text:
                lines[i] = f"{text}\t{weight}"
                self._write(PERSONAL_FILE, eol.join(lines))
                return
        self._write(PERSONAL_FILE, self._append_line(raw, f"{text}\t{weight}"))

    def delete_personal(self, text):
        raw = self._read(PERSONAL_FILE)
        eol = self._eol(raw)
        lines = raw.split(eol)
        start = self._body_start(lines)
        kept = lines[:start] + [ln for ln in lines[start:]
                                if ln.startswith("#") or not ln or ln.split("\t")[0] != text]
        if len(kept) == len(lines):
            raise ValueError("文件里已没有这个词条")
        self._write(PERSONAL_FILE, eol.join(kept))

    # ---------- 联想 ----------
    def _predict_table(self):
        order, table = [], {}
        for line in self._read(PREDICT_FILE).splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            p = line.split("\t")
            if len(p) < 2:
                continue
            if p[0] not in table:
                table[p[0]] = ([], [])
                order.append(p[0])
            if p[1].startswith("!"):
                table[p[0]][1].append(p[1][1:])
            else:
                table[p[0]][0].append(p[1])
        return order, table

    def get_predict(self, head):
        _, table = self._predict_table()
        pins, hidden = table.get(head, ([], []))
        return list(pins), list(hidden), list(self.db_predict.get(head, []))

    def set_predict(self, head, pins, hidden=()):
        head = self._clean(head, "前词")
        clean_pins = []
        for word in pins:
            word = self._clean(word, "联想词")
            if word.startswith("!"):
                raise ValueError("联想词不能以 ! 开头")
            if word not in clean_pins:
                clean_pins.append(word)
        clean_hidden = []
        for word in hidden:
            word = self._clean(word, "联想词")
            if word not in clean_hidden and word not in clean_pins:
                clean_hidden.append(word)
        order, table = self._predict_table()
        if head not in table:
            order.append(head)
        table[head] = (clean_pins, clean_hidden)
        out = [PREDICT_HEADER.rstrip("\n")]
        for key in order:
            out += [f"{key}\t{w}" for w in table[key][0]]
            out += [f"{key}\t!{w}" for w in table[key][1]]
        self._write(PREDICT_FILE, "\n".join(out) + "\n")

    def predict_heads(self):
        order, _ = self._predict_table()
        return order
