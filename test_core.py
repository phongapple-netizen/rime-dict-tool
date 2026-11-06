"""在临时副本上测试读写逻辑和界面操作，不碰正在使用的 Rime 文件夹。"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rime_dict_core import Store, move_db_predict, predict_view, rime_user_dir  # noqa: E402

SOURCE = rime_user_dir()
FILES = ["custom_phrase.txt", "wubi86_personal.dict.yaml", "wubi86.dict.yaml", "installation.yaml"]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "Rime")
        os.makedirs(self.root)
        for name in FILES:
            shutil.copy2(os.path.join(SOURCE, name), self.root)
        self.backups = os.path.join(self.tmp, "backups")
        self.store = Store(root=self.root, backup_root=self.backups)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def read(self, name):
        with open(os.path.join(self.root, name), encoding="utf-8", newline="") as f:
            return f.read()


class CoreTest(Base):
    def test_auto_code_matches_base_table(self):
        rows = [e for e in self.store.base if 2 <= len(e.text) <= 8 and len(e.code) == 4][:20000]
        good = sum(self.store.auto_code(e.text) == e.code for e in rows)
        self.assertGreater(good / len(rows), 0.95, f"{good}/{len(rows)}")
        self.assertEqual(self.store.auto_code("安全"), "pvwg")

    def test_search_word_and_code(self):
        self.assertTrue(any(e.text == "安全" and e.code == "pvwg" for e in self.store.search("安全")))
        self.assertTrue(any(e.text == "安全" for e in self.store.search("pvwg")))
        self.assertEqual(self.store.search("  "), [])

    def test_phrase_add_edit_delete_preserves_other_lines(self):
        before = self.read("custom_phrase.txt")
        self.store.upsert_phrase("测试词语", "qqqq", 123)
        self.assertIn("测试词语\tqqqq\t123", self.read("custom_phrase.txt"))
        self.store.upsert_phrase("测试词语2", "qqqw", 456, old_text="测试词语", old_code="qqqq")
        text = self.read("custom_phrase.txt")
        self.assertNotIn("测试词语\tqqqq", text)
        self.assertIn("测试词语2\tqqqw\t456", text)
        self.store.delete_phrase("测试词语2", "qqqw")
        self.assertEqual(self.read("custom_phrase.txt").rstrip(), before.rstrip())
        self.assertTrue(os.listdir(self.backups))

    def test_invalid_input_changes_nothing(self):
        before = self.read("custom_phrase.txt")
        for text, code in (("", "aa"), ("词", "a1"), ("词", ""), ("a\tb", "aa"), ("词", "中文")):
            with self.assertRaises(ValueError):
                self.store.upsert_phrase(text, code)
        with self.assertRaises(ValueError):
            self.store.upsert_phrase("词", "aa", -1)
        self.assertEqual(self.read("custom_phrase.txt"), before)

    def test_pin_to_top_beats_other_phrases(self):
        self.store.upsert_phrase("甲词", "qqqq", 5000000)
        self.store.pin_to_top("乙词", "qqqq")
        weights = {e.text: e.weight for e in self.store.phrases() if e.code == "qqqq"}
        self.assertGreater(weights["乙词"], weights["甲词"])

    def test_personal_add_update_delete(self):
        before = self.read("wubi86_personal.dict.yaml")
        self.store.upsert_personal("安全测试词", 777)
        self.assertIn("安全测试词\t777", self.read("wubi86_personal.dict.yaml"))
        self.store.upsert_personal("安全测试词", 888)
        self.assertEqual(self.read("wubi86_personal.dict.yaml").count("安全测试词"), 1)
        self.store.delete_personal("安全测试词")
        self.assertEqual(self.read("wubi86_personal.dict.yaml").rstrip(), before.rstrip())
        with self.assertRaises(ValueError):
            self.store.upsert_personal("😀😀")

    def test_predict_round_trip(self):
        self.store.set_predict("安全", ["隐患", "生产", "隐患"], ["测试"])
        self.store.set_predict("工", ["作"])
        self.store.set_predict("安全", ["生产", "隐患"], ["测试"])
        pins, hidden, db = self.store.get_predict("安全")
        self.assertEqual((pins, hidden), (["生产", "隐患"], ["测试"]))
        self.assertTrue(self.store.get_predict("工")[2])
        self.assertEqual(self.store.predict_heads(), ["安全", "工"])
        self.assertIn("安全\t!测试", self.read("predict_user.tsv"))
        with self.assertRaises(ValueError):
            self.store.set_predict("工", ["!坏"])


class MoveDbTest(unittest.TestCase):
    DB = ["作", "程", "具", "业", "艺"]

    def test_move_up_pins_prefix(self):
        pins = move_db_predict([], [], self.DB, "具", -1)
        self.assertEqual(pins, ["作", "具"])
        self.assertEqual(predict_view(pins, [], self.DB), ["作", "具", "程", "业", "艺"])
        pins = move_db_predict(pins, [], self.DB, "具", -1)
        self.assertEqual(pins, ["具"])
        self.assertEqual(predict_view(pins, [], self.DB), ["具", "作", "程", "业", "艺"])

    def test_move_down_past_unpinned(self):
        pins = move_db_predict([], [], self.DB, "作", 1)
        self.assertEqual(pins, ["程"])
        self.assertEqual(predict_view(pins, [], self.DB), ["程", "作", "具", "业", "艺"])

    def test_moving_back_clears_pins(self):
        pins = move_db_predict([], [], self.DB, "程", -1)
        self.assertEqual(pins, ["程"])
        self.assertEqual(move_db_predict(pins, [], self.DB, "程", 1), [])

    def test_edges_and_hidden_change_nothing(self):
        self.assertEqual(move_db_predict([], [], self.DB, "作", -1), [])
        self.assertEqual(move_db_predict([], [], self.DB, "艺", 1), [])
        self.assertEqual(move_db_predict([], ["程"], self.DB, "程", -1), [])
        self.assertEqual(move_db_predict([], [], self.DB, "不存在", 1), [])

    def test_skips_hidden_and_keeps_own_words(self):
        pins = move_db_predict(["作坊"], ["程"], self.DB, "具", -1)
        self.assertEqual(pins, ["作坊", "具"])
        self.assertEqual(predict_view(pins, ["程"], self.DB), ["具", "作", "业", "艺", "程"])
        pins = move_db_predict(pins, ["程"], self.DB, "作", -1)
        self.assertEqual(pins, ["作坊"])


class UiTest(Base):
    def test_db_move_buttons(self):
        from importlib.machinery import SourceFileLoader
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rime_dict_tool.pyw")
        module = SourceFileLoader("rime_dict_tool", path).load_module()  # noqa: 测试用
        self.store.db_predict["工"] = ["作", "程", "具"]
        app = module.App(store=self.store, confirm=False)
        try:
            app.p_head.set("工")
            app.load_predict()
            app.db_list.selection_set(2)
            app.db_move(-1)
            self.assertEqual(app.db_words, ["作", "具", "程"])
            self.assertEqual(app.selected_db(), "具")
            self.assertIn("工\t具", self.read("predict_user.tsv"))
            app.db_move(-1)
            self.assertEqual(app.db_words, ["具", "作", "程"])
            self.assertEqual(app.selected_db(), "具")
            app.db_move(-1)
            self.assertEqual(app.db_words, ["具", "作", "程"])
            self.assertEqual(self.read("predict_user.tsv").count("工\t"), 1)
            self.assertEqual(self.store.get_predict("工")[0], ["具"])
            app.load_predict()
            self.assertEqual(app.db_words, ["具", "作", "程"])
            app.db_list.selection_clear(0, "end")
            app.db_list.selection_set(2)
            app.hide_db()
            self.assertEqual(app.db_words, ["具", "作", "程"])
            app.db_list.selection_set(2)
            before = self.read("predict_user.tsv")
            app.db_move(-1)
            self.assertEqual(self.read("predict_user.tsv"), before)
            self.assertIn("取消隐藏", app.status.get())
            app.update()
            shot = os.environ.get("RIME_TOOL_SHOT")
            if shot:
                app.tabs.select(1)
                app.lift()
                app.attributes("-topmost", True)
                app.update()
                app.after(400)
                app.update()
                from PIL import ImageGrab
                box = (app.winfo_rootx(), app.winfo_rooty(),
                       app.winfo_rootx() + app.winfo_width(), app.winfo_rooty() + app.winfo_height())
                ImageGrab.grab(box).save(f"{shot}_dbmove.png")
        finally:
            app.destroy()

    def test_ui_flow(self):
        from importlib.machinery import SourceFileLoader
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rime_dict_tool.pyw")
        module = SourceFileLoader("rime_dict_tool", path).load_module()  # noqa: 测试用
        app = module.App(store=self.store, confirm=False)
        try:
            app.query.set("安全")
            app.search()
            self.assertTrue(app.tree.get_children())
            app.f_text.set("新造词语")
            app.f_code.set("pvwg")
            self.assertIn("重码", app.form_hint.get())
            app.save_word()
            self.assertIn("新造词语\tpvwg\t1000000", self.read("custom_phrase.txt"))
            first = app.tree.get_children()[0]
            app.tree.selection_set(first)
            app.update()
            app.load_selected()
            self.assertEqual(app.f_text.get(), "新造词语")
            app.f_weight.set("42")
            app.save_word()
            self.assertIn("新造词语\tpvwg\t42", self.read("custom_phrase.txt"))
            app.tree.selection_set(app.tree.get_children()[0])
            app.update()
            app.delete_selected()
            self.assertNotIn("新造词语", self.read("custom_phrase.txt"))

            app.f_text.set("无编码新词")
            self.assertIn("自动编码", app.form_hint.get())
            app.save_word()
            self.assertIn("无编码新词\t900000", self.read("wubi86_personal.dict.yaml"))

            app.p_head.set("工")
            app.load_predict()
            self.assertTrue(app.db_words)
            app.p_word.set("作坊")
            app.pin_add()
            app.db_list.selection_set(0)
            app.pin_from_db()
            app.pin_list.selection_clear(0, "end")
            app.pin_list.selection_set(1)
            app.pin_move(-1)
            self.assertEqual(app.pins[1], "作坊")
            app.db_list.selection_clear(0, "end")
            app.db_list.selection_set(1)
            hidden = app.db_words[1]
            app.hide_db()
            self.assertIn(f"工\t!{hidden}", self.read("predict_user.tsv"))
            app.update()
            shot = os.environ.get("RIME_TOOL_SHOT")
            if shot:
                self.capture(app, shot)
        finally:
            app.destroy()

    @staticmethod
    def capture(app, path):
        from PIL import ImageGrab
        for index, name in ((0, "word"), (1, "predict")):
            app.tabs.select(index)
            if index == 0:
                app.query.set("安全")
                app.search()
            app.lift()
            app.attributes("-topmost", True)
            app.update()
            app.after(400)
            app.update()
            box = (app.winfo_rootx(), app.winfo_rooty(),
                   app.winfo_rootx() + app.winfo_width(), app.winfo_rooty() + app.winfo_height())
            ImageGrab.grab(box).save(f"{path}_{name}.png")


if __name__ == "__main__":
    unittest.main(verbosity=2)
