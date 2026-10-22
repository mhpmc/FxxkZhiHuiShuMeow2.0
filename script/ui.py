"""智慧树小助手 UI（Tkinter）。

- 列出智慧课程 + 翻转课，逐门勾选“刷课 / 测验作业”
- DeepSeek API 设置存 script/config.json
- 作业/测验：AI 先出答案 -> 界面确认（可改）-> 仅保存草稿 / 确认提交 / 取消
"""
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

import ai

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable
NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

CHECK = '☑'
UNCHECK = '☐'
FONT = ('Microsoft YaHei UI', 10)
FONT_BOLD = ('Microsoft YaHei UI', 10, 'bold')
TITLE_FONT = ('Microsoft YaHei UI', 17, 'bold')
MONO_FONT = ('Consolas', 9)

ACCENT = '#2f6feb'
OK_BG = '#e7f7ee'
WARN_BG = '#fff7e0'
BAD_BG = '#ffecec'


class Job:
    def __init__(self, args, sink):
        self.args = args
        self.sink = sink
        self.queue = queue.Queue()
        env = dict(os.environ)
        env['PYTHONUTF8'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'
        self.proc = subprocess.Popen(
            [PYTHON, *args], cwd=str(HERE), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace', bufsize=1,
            creationflags=NO_WINDOW)
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        try:
            for line in self.proc.stdout:
                self.queue.put(line.rstrip('\r\n'))
        finally:
            self.queue.put(None)

    def send(self, payload):
        if self.proc.stdin:
            try:
                self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + '\n')
                self.proc.stdin.flush()
            except Exception as error:
                self.sink(f'发送失败：{error}')

    def stop(self):
        try:
            self.proc.terminate()
        except Exception:
            pass


class App:
    def __init__(self, root):
        self.root = root
        self.root.title('智慧树小助手')
        self.root.geometry('1180x840')
        self.root.minsize(980, 700)
        self.jobs = []
        self.current = None
        self.pending = []
        self.answer_queue = []
        self.courses = {}
        self.homeworks = {}
        config = ai.load_config()
        self.var_key = tk.StringVar(value=config.get('deepseek_api_key', ''))
        self.var_base = tk.StringVar(value=config.get('base_url', ai.DEFAULT_BASE))
        self.var_model = tk.StringVar(value=config.get('model', ai.DEFAULT_MODEL))
        self.status = tk.StringVar(value='就绪')
        self._style()
        self._build()
        self.root.after(120, self.poll)

    # ---------- 外观 ----------
    def _style(self):
        style = ttk.Style()
        for theme in ('clam', 'vista', 'default'):
            try:
                style.theme_use(theme)
                break
            except Exception:
                continue
        style.configure('.', font=FONT)
        style.configure('TButton', padding=(12, 6), font=FONT)
        style.configure('TLabel', font=FONT)
        style.configure('TLabelframe.Label', font=FONT_BOLD, foreground='#253858')
        style.configure('Treeview', rowheight=30, font=FONT, background='#ffffff',
                        fieldbackground='#ffffff')
        style.configure('Treeview.Heading', font=FONT_BOLD, padding=(6, 6))
        style.map('Treeview', background=[('selected', '#d7e7ff')],
                  foreground=[('selected', '#10233f')])

    def _build(self):
        header = tk.Frame(self.root, bg=ACCENT, height=58)
        header.pack(fill='x')
        tk.Label(header, text='智慧树小助手', bg=ACCENT, fg='white',
                 font=TITLE_FONT).pack(side='left', padx=16, pady=10)
        tk.Label(header, text='智慧课程 / 翻转课 · DeepSeek 智能答题', bg=ACCENT,
                 fg='#dbe9ff', font=FONT).pack(side='left')

        body = ttk.Frame(self.root, padding=(10, 8))
        body.pack(fill='both', expand=True)

        settings = ttk.LabelFrame(body, text='DeepSeek 官方 API', padding=8)
        settings.pack(fill='x')
        ttk.Label(settings, text='API Key').grid(row=0, column=0, sticky='w', padx=(0, 6))
        ttk.Entry(settings, textvariable=self.var_key, width=46, show='*').grid(
            row=0, column=1, padx=4, sticky='we')
        ttk.Button(settings, text='保存', command=self.save_config).grid(row=0, column=2, padx=4)
        ttk.Button(settings, text='测试连通', command=self.test_api).grid(row=0, column=3, padx=4)
        ttk.Label(settings, text='Base URL').grid(row=1, column=0, sticky='w', padx=(0, 6), pady=(4, 0))
        ttk.Entry(settings, textvariable=self.var_base, width=46).grid(
            row=1, column=1, padx=4, pady=(4, 0), sticky='we')
        ttk.Label(settings, text='模型').grid(row=1, column=2, padx=4, pady=(4, 0))
        ttk.Entry(settings, textvariable=self.var_model, width=18).grid(
            row=1, column=3, padx=4, pady=(4, 0), sticky='we')
        settings.columnconfigure(1, weight=1)

        toolbar = ttk.Frame(body)
        toolbar.pack(fill='x', pady=(8, 2))
        for text, command in (('读取课程', self.load_courses),
                              ('全选刷课', lambda: self.set_all(True)),
                              ('全不选', lambda: self.set_all(False)),
                              ('开始刷课', self.start_brush),
                              ('读取作业/测验', self.load_homework),
                              ('AI 答题（选中）', self.start_answer),
                              ('停止', self.stop_current)):
            ttk.Button(toolbar, text=text, command=command).pack(side='left', padx=3)

        hint = ttk.Label(body, text='提示：点表格里的 ☐ 切换勾选；AI 只给答案，提交前请自己再看一眼。',
                         foreground='#5b6b85')
        hint.pack(fill='x', pady=(0, 4))

        course_box = ttk.LabelFrame(body, text='课程', padding=6)
        course_box.pack(fill='both', expand=True)
        columns = ('source', 'name', 'brush', 'work')
        self.course_tree = ttk.Treeview(course_box, columns=columns, show='headings', height=7)
        for key, text, width, anchor in (('source', '来源', 110, 'center'),
                                         ('name', '课程', 620, 'w'),
                                         ('brush', '刷课', 90, 'center'),
                                         ('work', '测验作业', 100, 'center')):
            self.course_tree.heading(key, text=text)
            self.course_tree.column(key, width=width, anchor=anchor)
        self.course_tree.pack(fill='both', expand=True)
        self.course_tree.bind('<Button-1>', self.toggle_course)

        hw_box = ttk.LabelFrame(body, text='作业 / 测验（勾选要 AI 处理的条目）', padding=6)
        hw_box.pack(fill='both', expand=True, pady=(8, 0))
        hw_columns = ('course', 'title', 'status', 'select')
        self.hw_tree = ttk.Treeview(hw_box, columns=hw_columns, show='headings', height=7)
        for key, text, width, anchor in (('course', '课程', 280, 'w'),
                                         ('title', '标题', 480, 'w'),
                                         ('status', '状态', 110, 'center'),
                                         ('select', '选择', 90, 'center')):
            self.hw_tree.heading(key, text=text)
            self.hw_tree.column(key, width=width, anchor=anchor)
        self.hw_tree.pack(fill='both', expand=True)
        self.hw_tree.bind('<Button-1>', self.toggle_homework)

        log_box = ttk.LabelFrame(body, text='日志', padding=6)
        log_box.pack(fill='both', expand=True, pady=(8, 0))
        self.log_text = scrolledtext.ScrolledText(log_box, height=10, state='disabled',
                                                  font=MONO_FONT, background='#fbfcfe',
                                                  relief='flat')
        self.log_text.pack(fill='both', expand=True)

        status_bar = tk.Frame(self.root, bg='#eef2f8')
        status_bar.pack(fill='x')
        tk.Label(status_bar, textvariable=self.status, bg='#eef2f8', fg='#33415c',
                 font=FONT, anchor='w').pack(fill='x', padx=12, pady=4)

    def log(self, text):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', str(text) + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    # ---------- 配置 ----------
    def save_config(self):
        ai.save_config({'deepseek_api_key': self.var_key.get().strip(),
                        'base_url': self.var_base.get().strip(),
                        'model': self.var_model.get().strip()})
        self.log('DeepSeek 配置已保存到 script/config.json（打包发送前记得删掉）')

    def test_api(self):
        self.save_config()

        def run():
            try:
                client = ai.DeepSeek(self.var_key.get(), self.var_base.get(), self.var_model.get())
                self.root.after(0, self.log, 'DeepSeek 测试：' + str(client.test()).strip())
            except ai.AiError as error:
                self.root.after(0, self.log, f'DeepSeek 测试失败：{error}')

        threading.Thread(target=run, daemon=True).start()

    # ---------- 进程 ----------
    def start(self, args, interactive=False):
        job = Job(args, self.log)
        self.jobs.append(job)
        self.current = job
        self.status.set('运行中：' + ' '.join(args))
        self.log('> ' + ' '.join(args))
        return job

    def stop_current(self):
        if self.current:
            self.current.stop()
            self.log('已请求停止')
        self.pending = []
        self.answer_queue = []
        self.status.set('已停止')

    def poll(self):
        for job in list(self.jobs):
            finished = False
            while True:
                try:
                    line = job.queue.get_nowait()
                except queue.Empty:
                    break
                if line is None:
                    finished = True
                    break
                self.handle_line(job, line)
            if finished:
                self.jobs.remove(job)
                if job is self.current:
                    self.current = None
                    self.status.set('就绪')
                    if self.pending:
                        self.start(self.pending.pop(0))
                    elif self.answer_queue:
                        self.start_answer_next()
                try:
                    job.proc.wait(timeout=1)
                except Exception:
                    pass
        self.root.after(120, self.poll)

    def handle_line(self, job, line):
        text = line.strip()
        if not text:
            return
        if not text.startswith('{'):
            self.log(text)
            return
        try:
            data = json.loads(text)
        except Exception:
            self.log(text)
            return
        event = data.get('event')
        if event == 'log':
            self.log(data.get('text', ''))
        elif event == 'courses':
            self.fill_courses(data)
        elif event == 'homework':
            self.fill_homework(data)
        elif event == 'questions':
            self.on_questions(job, data)
        elif event == 'await':
            pass
        elif event == 'saved':
            self.log('草稿已保存：' + str(data.get('message')))
        elif event == 'submitted':
            self.log('提交结果：' + str(data.get('message')))
        elif event == 'skipped':
            self.log('已跳过：' + str(data.get('message')))
        elif event == 'error':
            self.log('出错：' + str(data.get('message')))

    # ---------- 课程表 ----------
    def fill_courses(self, data):
        self.course_tree.delete(*self.course_tree.get_children())
        self.courses.clear()
        for item in data.get('smart') or []:
            iid = 'smart:' + item['id']
            self.courses[iid] = {'source': 'smart', 'id': item['id'],
                                 'class_id': item.get('class_id'), 'name': item['name'],
                                 'brush': False, 'work': False}
            self.course_tree.insert('', 'end', iid=iid, values=(
                '智慧课程', item['name'], UNCHECK, UNCHECK))
        for item in data.get('flip') or []:
            iid = 'flip:' + item['id']
            self.courses[iid] = {'source': 'flip', 'id': item['id'],
                                 'name': item['name'], 'brush': False, 'work': False}
            self.course_tree.insert('', 'end', iid=iid, values=(
                '翻转课', item['name'], UNCHECK, UNCHECK))
        self.log(f"课程：智慧课程 {len(data.get('smart') or [])} 门，"
                 f"翻转课 {len(data.get('flip') or [])} 门")

    def toggle_course(self, event):
        if self.course_tree.identify('region', event.x, event.y) != 'cell':
            return
        iid = self.course_tree.identify_row(event.y)
        column = self.course_tree.identify_column(event.x)
        if not iid or column not in ('#3', '#4'):
            return
        item = self.courses.get(iid)
        if not item:
            return
        key = 'brush' if column == '#3' else 'work'
        item[key] = not item[key]
        values = list(self.course_tree.item(iid, 'values'))
        values[2] = CHECK if item['brush'] else UNCHECK
        values[3] = CHECK if item['work'] else UNCHECK
        self.course_tree.item(iid, values=values)

    def set_all(self, value):
        for iid, item in self.courses.items():
            item['brush'] = value
            values = list(self.course_tree.item(iid, 'values'))
            values[2] = CHECK if value else UNCHECK
            self.course_tree.item(iid, values=values)

    # ---------- 作业表 ----------
    def fill_homework(self, data):
        course = next((c for c in self.courses.values() if c['id'] == data.get('course_id')), None)
        course_name = course['name'] if course else data.get('course_id')
        for item in data.get('items') or []:
            status = item.get('status')
            label = {1: '未做', 3: '待批阅', 4: '已批阅'}.get(status, str(status))
            iid = f"{data.get('course_id')}:{item['homework_id']}"
            selectable = status == 1
            self.homeworks[iid] = {'course_id': data.get('course_id'), 'title': item['title'],
                                   'homework_id': item['homework_id'], 'status': status,
                                   'selected': False, 'selectable': selectable}
            self.hw_tree.insert('', 'end', iid=iid, values=(
                course_name, item['title'], label, UNCHECK))
        self.log(f"作业/测验：{course_name} 共 {len(data.get('items') or [])} 条")

    def toggle_homework(self, event):
        if self.hw_tree.identify('region', event.x, event.y) != 'cell':
            return
        iid = self.hw_tree.identify_row(event.y)
        column = self.hw_tree.identify_column(event.x)
        if not iid or column != '#4':
            return
        item = self.homeworks.get(iid)
        if not item or not item['selectable']:
            return
        item['selected'] = not item['selected']
        values = list(self.hw_tree.item(iid, 'values'))
        values[3] = CHECK if item['selected'] else UNCHECK
        self.hw_tree.item(iid, values=values)

    # ---------- 动作 ----------
    def load_courses(self):
        if self.current:
            self.log('已有任务在跑，先等它结束')
            return
        self.start([str(HERE / 'worker.py'), 'list', '--show', '--timeout', '600'])

    def start_brush(self):
        if self.current:
            self.log('已有任务在跑')
            return
        smart = [c['id'] for c in self.courses.values() if c['brush'] and c['source'] == 'smart']
        flip = [c['id'] for c in self.courses.values() if c['brush'] and c['source'] == 'flip']
        args = [str(HERE / 'run.py')]
        if smart:
            for cid in smart:
                args += ['--course', cid]
        else:
            args += ['--no-smart']
        if flip:
            for cid in flip:
                args += ['--flip-course', cid]
        else:
            args += ['--no-flip']
        self.start(args)

    def load_homework(self):
        if self.current:
            self.log('已有任务在跑')
            return
        courses = [c['id'] for c in self.courses.values() if c['work']]
        if not courses:
            self.log('先在课程表里勾选“测验作业”列')
            return
        self.hw_tree.delete(*self.hw_tree.get_children())
        self.homeworks.clear()
        self.pending = [[str(HERE / 'worker.py'), 'homework', '--course', cid] for cid in courses]
        self.start(self.pending.pop(0))

    def start_answer(self):
        if self.current:
            self.log('已有任务在跑')
            return
        selected = [h for h in self.homeworks.values() if h['selected']]
        if not selected:
            self.log('先在作业表里勾选要处理的条目')
            return
        self.answer_queue = selected
        self.start_answer_next()

    def start_answer_next(self):
        if not self.answer_queue:
            return
        item = self.answer_queue.pop(0)
        self.log(f"处理：{item['title']}")
        self.start([str(HERE / 'worker.py'), 'answer',
                    '--course', item['course_id'],
                    '--homework', item['homework_id'],
                    '--title', item['title']], interactive=True)

    # ---------- AI 与确认 ----------
    def on_questions(self, job, data):
        questions = data['questions']
        self.log(f"抓到 {len(questions)} 道题，正在问 DeepSeek…")
        course = next((c for c in self.courses.values() if c['id'] == data.get('course_id')), {})
        prompt = [{'id': str(q['index']), 'type': q['type_name'], 'stem': q['content'],
                   'options': [{'letter': o['letter'], 'text': o['text']} for o in q['options']]}
                  for q in questions]

        def run():
            try:
                client = ai.DeepSeek(self.var_key.get(), self.var_base.get(), self.var_model.get())
                answers = client.answer_questions(prompt, course.get('name', ''))
            except ai.AiError as error:
                self.root.after(0, self.log, f'AI 失败：{error}')
                self.root.after(0, lambda: job.send({'action': 'skip'}))
                return
            self.root.after(0, self.show_review, job, questions, answers)

        threading.Thread(target=run, daemon=True).start()

    def show_review(self, job, questions, answers):
        mapping = {}
        for item in answers:
            try:
                mapping[int(item.get('id', -1))] = str(item.get('answer', '')).strip()
            except Exception:
                continue
        reason = {}
        for item in answers:
            try:
                reason[int(item.get('id', -1))] = (item.get('confidence'), item.get('reason'))
            except Exception:
                continue

        window = tk.Toplevel(self.root)
        window.title('AI 答案确认（可以改，确认后才提交）')
        window.geometry('1040x680')
        window.transient(self.root)

        info = ttk.Label(window, text='绿色=把握高、黄色=中等、红色=偏低；选中某题可在下面改答案。',
                         foreground='#5b6b85')
        info.pack(fill='x', padx=10, pady=(8, 2))

        columns = ('no', 'type', 'stem', 'answer', 'conf')
        tree = ttk.Treeview(window, columns=columns, show='headings')
        for key, text, width, anchor in (('no', '题号', 56, 'center'),
                                         ('type', '题型', 110, 'center'),
                                         ('stem', '题目', 520, 'w'),
                                         ('answer', 'AI 答案', 160, 'w'),
                                         ('conf', '把握', 70, 'center')):
            tree.heading(key, text=text)
            tree.column(key, width=width, anchor=anchor)
        tree.tag_configure('high', background=OK_BG)
        tree.tag_configure('mid', background=WARN_BG)
        tree.tag_configure('low', background=BAD_BG)
        tree.pack(fill='both', expand=True, padx=10)

        def row_tag(index):
            confidence = reason.get(index, (None, None))[0]
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                return 'mid'
            if confidence >= 0.8:
                return 'high'
            if confidence >= 0.5:
                return 'mid'
            return 'low'

        state = {}
        for question in questions:
            index = question['index']
            value = mapping.get(index, '')
            state[index] = value
            tree.insert('', 'end', iid=str(index), tags=(row_tag(index),), values=(
                index + 1, question['type_name'], question['content'],
                value, reason.get(index, ('', ''))[0]))

        editor = ttk.LabelFrame(window, text='修改选中题的答案', padding=6)
        editor.pack(fill='x', padx=10, pady=6)
        edit_var = tk.StringVar()
        entry = ttk.Entry(editor, textvariable=edit_var)
        entry.pack(side='left', fill='x', expand=True, padx=(0, 6))
        detail = ttk.Label(window, text='', foreground='#33415c', wraplength=980,
                           justify='left')
        detail.pack(fill='x', padx=12)

        def on_select(_event=None):
            selection = tree.selection()
            if not selection:
                return
            index = int(selection[0])
            edit_var.set(state.get(index, ''))
            question = questions[index]
            options = '  '.join(f"{o['letter']} {o['text']}" for o in question['options'])
            detail.configure(text=(question['content'] + '\n' + options)[:900])

        tree.bind('<<TreeviewSelect>>', on_select)

        def apply_edit():
            selection = tree.selection()
            if not selection:
                return
            index = int(selection[0])
            state[index] = edit_var.get().strip()
            values = list(tree.item(str(index), 'values'))
            values[3] = state[index]
            tree.item(str(index), values=values)

        ttk.Button(editor, text='应用到选中题', command=apply_edit).pack(side='left')

        buttons = ttk.Frame(window)
        buttons.pack(pady=(2, 12))
        payload = [{'index': index, 'answer': value} for index, value in state.items()]

        def send(action):
            answer_list = [{'index': index, 'answer': state.get(index, '')}
                           for index in sorted(state)]
            job.send({'action': action, 'answers': answer_list})
            self.log('已把答案交给接口处理，动作：' + ('提交' if action == 'submit' else '仅保存草稿'))
            window.destroy()

        ttk.Button(buttons, text='仅保存草稿', command=lambda: send('save')).pack(side='left', padx=8)
        ttk.Button(buttons, text='确认提交', command=lambda: send('submit')).pack(side='left', padx=8)
        ttk.Button(buttons, text='取消', command=lambda: (
            job.send({'action': 'skip'}), self.log('已取消'), window.destroy())).pack(
            side='left', padx=8)

        if questions:
            tree.selection_set(str(questions[0]['index']))
            on_select()
        del payload


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()