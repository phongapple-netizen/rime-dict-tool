"""Rime 词库工具：查词、自定义编码、调序、编辑联想。"""
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk

from rime_dict_core import (DEFAULT_PERSONAL_WEIGHT, DEFAULT_PHRASE_WEIGHT, SOURCE_LABELS, Store,
                            deployer_path)


class App(tk.Tk):
    def __init__(self, store=None, confirm=True):
        super().__init__()
        self.title("Rime 词库工具")
        self.geometry("920x640")
        self.minsize(760, 520)
        self.store = store or Store()
        self.confirm = confirm
        self.results = []
        self.editing = None
        self.head = None
        self.pins = []
        self.hidden = []
        self.db_words = []
        self.status = tk.StringVar(value="就绪。修改后点右下角“重新部署”才会生效。")

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.tabs = tabs
        self.word_tab = ttk.Frame(tabs, padding=8)
        self.predict_tab = ttk.Frame(tabs, padding=8)
        tabs.add(self.word_tab, text="查词与编码")
        tabs.add(self.predict_tab, text="联想编辑")
        self._build_word_tab()
        self._build_predict_tab()

        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        ttk.Label(bar, textvariable=self.status).pack(side="left", fill="x", expand=True)
        self.deploy_button = ttk.Button(bar, text="重新部署", command=self.deploy)
        self.deploy_button.pack(side="right")

    # ---------- 查词与编码 ----------
    def _build_word_tab(self):
        top = ttk.Frame(self.word_tab)
        top.pack(fill="x")
        ttk.Label(top, text="查词语或编码：").pack(side="left")
        self.query = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.query, width=30)
        entry.pack(side="left", padx=4)
        entry.bind("<Return>", lambda _e: self.search())
        ttk.Button(top, text="查询", command=self.search).pack(side="left")
        self.result_info = tk.StringVar()
        ttk.Label(top, textvariable=self.result_info).pack(side="left", padx=10)

        table = ttk.Frame(self.word_tab)
        table.pack(fill="both", expand=True, pady=8)
        cols = ("text", "code", "weight", "source")
        self.tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="browse")
        for col, label, width in (("text", "词语", 300), ("code", "编码", 120),
                                  ("weight", "权重/次数", 120), ("source", "来源", 170)):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="w")
        scroll = ttk.Scrollbar(table, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.update_row_buttons())
        self.tree.bind("<Double-1>", lambda _e: self.load_selected())

        row = ttk.Frame(self.word_tab)
        row.pack(fill="x")
        self.top_button = ttk.Button(row, text="排到该编码首位", command=self.pin_selected)
        self.edit_button = ttk.Button(row, text="编辑", command=self.load_selected)
        self.delete_button = ttk.Button(row, text="删除", command=self.delete_selected)
        for button in (self.top_button, self.edit_button, self.delete_button):
            button.pack(side="left", padx=(0, 6))
            button.state(["disabled"])

        form = ttk.LabelFrame(self.word_tab, text="新增或修改词条", padding=8)
        form.pack(fill="x", pady=(8, 0))
        self.f_text, self.f_code, self.f_weight = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(form, text="词语").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.f_text, width=30).grid(row=0, column=1, padx=4, sticky="we")
        ttk.Label(form, text="编码").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.f_code, width=12).grid(row=0, column=3, padx=4)
        ttk.Label(form, text="权重").grid(row=0, column=4, sticky="w")
        ttk.Entry(form, textvariable=self.f_weight, width=12).grid(row=0, column=5, padx=4)
        ttk.Button(form, text="保存", command=self.save_word).grid(row=0, column=6, padx=4)
        ttk.Button(form, text="清空", command=self.clear_form).grid(row=0, column=7)
        form.columnconfigure(1, weight=1)
        self.form_hint = tk.StringVar()
        ttk.Label(form, textvariable=self.form_hint, wraplength=860).grid(
            row=1, column=0, columnspan=8, sticky="w", pady=(6, 0))
        self.f_text.trace_add("write", lambda *_: self.update_hint())
        self.f_code.trace_add("write", lambda *_: self.update_hint())
        self.update_hint()

    def search(self):
        query = self.query.get().strip()
        self.results = self.store.search(query)
        self.tree.delete(*self.tree.get_children())
        for i, e in enumerate(self.results):
            self.tree.insert("", "end", iid=str(i), values=(
                e.text, e.code or "（无法计算）", f"{e.weight:.0f}", SOURCE_LABELS[e.source]))
        count = len(self.results)
        self.result_info.set(f"{count} 条" + ("（只显示前 500 条）" if count >= 500 else ""))
        if not count and query and not query.isascii():
            self.clear_form()
            self.f_text.set(query)
        self.update_row_buttons()

    def selected(self):
        sel = self.tree.selection()
        return self.results[int(sel[0])] if sel else None

    def update_row_buttons(self):
        e = self.selected()
        editable = e is not None and e.source in ("phrase", "personal")
        self.top_button.state(["!disabled"] if e and e.code else ["disabled"])
        self.edit_button.state(["!disabled"] if editable else ["disabled"])
        self.delete_button.state(["!disabled"] if editable else ["disabled"])

    def load_selected(self):
        e = self.selected()
        if not e:
            return
        self.editing = e if e.source in ("phrase", "personal") else None
        self.f_text.set(e.text)
        self.f_code.set("" if e.source == "personal" else e.code)
        self.f_weight.set(f"{e.weight:.0f}" if e.source in ("phrase", "personal") else "")
        self.update_hint()

    def clear_form(self):
        self.editing = None
        self.f_text.set("")
        self.f_code.set("")
        self.f_weight.set("")

    def update_hint(self):
        text, code = self.f_text.get().strip(), self.f_code.get().strip().lower()
        if code:
            same = self.store.same_code(code, exclude_text=text)
            names = "、".join(dict.fromkeys(e.text for e in same[:8]))
            self.form_hint.set(f"重码 {len(same)} 个：{names}" if same else "这个编码目前没有其他词。")
        elif text:
            auto = self.store.auto_code(text)
            self.form_hint.set(f"将按五笔规则自动编码：{auto}" if auto else "有基础码表找不到的字，请手动填写编码。")
        else:
            self.form_hint.set("填了编码存到自定义短语；不填编码按五笔规则自动生成，存到个人词典。")

    def save_word(self):
        text, code = self.f_text.get().strip(), self.f_code.get().strip().lower()
        raw_weight = self.f_weight.get().strip()
        try:
            weight = int(float(raw_weight)) if raw_weight else None
            if code:
                same = self.store.same_code(code, exclude_text=text)
                if same and self.confirm and not messagebox.askyesno(
                        "有重码", f"编码 {code} 已有 {len(same)} 个其他词，仍要保存吗？"):
                    return
                old = self.editing if self.editing and self.editing.source == "phrase" else None
                self.store.upsert_phrase(
                    text, code, DEFAULT_PHRASE_WEIGHT if weight is None else weight,
                    old_text=old.text if old else None, old_code=old.code if old else None)
                if self.editing and self.editing.source == "personal":
                    self.store.delete_personal(self.editing.text)
            else:
                if self.editing and self.editing.source == "phrase":
                    raise ValueError("自定义短语必须有编码")
                old = self.editing if self.editing and self.editing.source == "personal" else None
                self.store.upsert_personal(
                    text, DEFAULT_PERSONAL_WEIGHT if weight is None else weight,
                    old_text=old.text if old else None)
        except (ValueError, OSError) as err:
            self.show_error(err)
            return
        self.query.set(text)
        self.clear_form()
        self.search()
        self.mark_dirty(f"已保存“{text}”。")

    def pin_selected(self):
        e = self.selected()
        if not e:
            return
        try:
            self.store.pin_to_top(e.text, e.code)
        except (ValueError, OSError) as err:
            self.show_error(err)
            return
        self.search()
        self.mark_dirty(f"“{e.text}”已写入自定义短语，将排到 {e.code} 首位。")

    def delete_selected(self):
        e = self.selected()
        if not e or e.source not in ("phrase", "personal"):
            return
        if self.confirm and not messagebox.askyesno(
                "确认删除", f"删除“{e.text}”（{SOURCE_LABELS[e.source]}）？"):
            return
        try:
            if e.source == "phrase":
                self.store.delete_phrase(e.text, e.code)
            else:
                self.store.delete_personal(e.text)
        except (ValueError, OSError) as err:
            self.show_error(err)
            return
        self.search()
        self.mark_dirty(f"已删除“{e.text}”。")

    # ---------- 联想 ----------
    def _build_predict_tab(self):
        top = ttk.Frame(self.predict_tab)
        top.pack(fill="x")
        ttk.Label(top, text="前词（打完它之后出现联想）：").pack(side="left")
        self.p_head = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.p_head, width=20)
        entry.pack(side="left", padx=4)
        entry.bind("<Return>", lambda _e: self.load_predict())
        ttk.Button(top, text="查看", command=self.load_predict).pack(side="left")
        self.p_info = tk.StringVar(value="输入一个字或词，然后点“查看”。")
        ttk.Label(top, textvariable=self.p_info).pack(side="left", padx=10)

        panes = ttk.Frame(self.predict_tab)
        panes.pack(fill="both", expand=True, pady=8)
        panes.columnconfigure(0, weight=1)
        panes.columnconfigure(2, weight=1)
        panes.rowconfigure(1, weight=1)

        ttk.Label(panes, text="我的联想（按此顺序排在最前）").grid(row=0, column=0, sticky="w")
        self.pin_list = tk.Listbox(panes, exportselection=False)
        self.pin_list.grid(row=1, column=0, sticky="nsew")

        mid = ttk.Frame(panes, padding=8)
        mid.grid(row=1, column=1)
        for label, command in (("上移", lambda: self.pin_move(-1)), ("下移", lambda: self.pin_move(1)),
                               ("移除", self.pin_remove), ("← 加入", self.pin_from_db),
                               ("隐藏 →", self.hide_db), ("取消隐藏", self.unhide_db)):
            ttk.Button(mid, text=label, command=command, width=10).pack(pady=3)

        ttk.Label(panes, text="词库现有联想（标“隐藏”的不会显示）").grid(row=0, column=2, sticky="w")
        self.db_list = tk.Listbox(panes, exportselection=False)
        self.db_list.grid(row=1, column=2, sticky="nsew")
        self.db_list.bind("<Double-1>", lambda _e: self.pin_from_db())

        bottom = ttk.Frame(self.predict_tab)
        bottom.pack(fill="x")
        ttk.Label(bottom, text="新联想词：").pack(side="left")
        self.p_word = tk.StringVar()
        word_entry = ttk.Entry(bottom, textvariable=self.p_word, width=24)
        word_entry.pack(side="left", padx=4)
        word_entry.bind("<Return>", lambda _e: self.pin_add())
        ttk.Button(bottom, text="添加", command=self.pin_add).pack(side="left")
        ttk.Label(bottom, text="改动立即保存；重新部署后生效。").pack(side="left", padx=12)

    def load_predict(self):
        head = self.p_head.get().strip()
        if not head:
            return
        self.head = head
        self.pins, self.hidden, self.db_words = self.store.get_predict(head)
        self.refresh_predict()

    def refresh_predict(self, select=None):
        self.pin_list.delete(0, "end")
        for word in self.pins:
            self.pin_list.insert("end", word)
        if select is not None and 0 <= select < len(self.pins):
            self.pin_list.selection_set(select)
        self.db_list.delete(0, "end")
        for word in self.db_words:
            self.db_list.insert("end", f"{word}（隐藏）" if word in self.hidden else word)
            if word in self.hidden:
                self.db_list.itemconfig("end", foreground="gray")
        note = f"词库有 {len(self.db_words)} 个联想" if self.db_words else "词库没有这个前词，只显示你加的词"
        self.p_info.set(f"“{self.head}”：{note}")

    def save_predict(self, message, select=None):
        try:
            self.store.set_predict(self.head, self.pins, self.hidden)
        except (ValueError, OSError) as err:
            self.show_error(err)
            self.load_predict()
            return
        self.refresh_predict(select)
        self.mark_dirty(message)

    def pin_add(self):
        if self.p_head.get().strip() != self.head:
            self.load_predict()
        word = self.p_word.get().strip()
        if not self.head or not word:
            return
        self.p_word.set("")
        if word in self.pins:
            return
        self.pins.append(word)
        if word in self.hidden:
            self.hidden.remove(word)
        self.save_predict(f"已给“{self.head}”添加联想“{word}”。", len(self.pins) - 1)

    def pin_move(self, delta):
        sel = self.pin_list.curselection()
        if not sel:
            return
        i, j = sel[0], sel[0] + delta
        if 0 <= j < len(self.pins):
            self.pins[i], self.pins[j] = self.pins[j], self.pins[i]
            self.save_predict("已调整联想顺序。", j)

    def pin_remove(self):
        sel = self.pin_list.curselection()
        if sel:
            word = self.pins.pop(sel[0])
            self.save_predict(f"已移除“{word}”。")

    def selected_db(self):
        sel = self.db_list.curselection()
        return self.db_words[sel[0]] if sel else None

    def pin_from_db(self):
        word = self.selected_db()
        if word and word not in self.pins:
            self.pins.append(word)
            if word in self.hidden:
                self.hidden.remove(word)
            self.save_predict(f"已把“{word}”加入我的联想。", len(self.pins) - 1)

    def hide_db(self):
        word = self.selected_db()
        if word and word not in self.hidden:
            if word in self.pins:
                self.pins.remove(word)
            self.hidden.append(word)
            self.save_predict(f"已隐藏“{word}”。")

    def unhide_db(self):
        word = self.selected_db()
        if word and word in self.hidden:
            self.hidden.remove(word)
            self.save_predict(f"已取消隐藏“{word}”。")

    # ---------- 其他 ----------
    def mark_dirty(self, message):
        self.status.set(message + " 点“重新部署”后生效。")

    def show_error(self, err):
        self.status.set(f"未保存：{err}")
        if self.confirm:
            messagebox.showerror("无法保存", str(err))

    def deploy(self):
        try:
            process = subprocess.Popen([deployer_path(), "/deploy"])
        except OSError as err:
            self.show_error(err)
            return
        self.deploy_button.state(["disabled"])
        self.status.set("正在部署……")

        def check():
            code = process.poll()
            if code is None:
                self.after(500, check)
                return
            self.deploy_button.state(["!disabled"])
            self.status.set("部署完成，可以打字试试。" if code == 0 else f"部署器返回错误 {code}。")

        check()


if __name__ == "__main__":
    App().mainloop()
