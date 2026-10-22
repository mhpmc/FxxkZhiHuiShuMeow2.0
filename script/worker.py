"""UI 的浏览器侧 worker。

- list：打开浏览器列智慧课程 + 翻转课（智慧课程列表必须借页面里的请求模块）
- homework / answer：完全不启动浏览器，只用保存的 cookie 向接口发数据包

answer 是交互式的：抓完题输出 {"event":"questions",...} 和 {"event":"await"}，
再从 stdin 读一行 JSON：
  {"action":"save",  "answers":[{"index":0,"answer":"C"},...]}   只保存草稿
  {"action":"submit","answers":[...]}                            保存并提交
  {"action":"skip"}                                              什么都不做
"""
import argparse
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
PROFILE = HERE / '.session'
STATE = PROFILE / 'auth-state.json'

OUT = sys.stdout
sys.stdout = sys.stderr  # 库里的 print 走 stderr，stdout 只留给协议

API = 'https://hiexam-server.zhihuishu.com/zhsathome'
PAPER = API + '/homeworkUserPaper'
LIST_API = API + '/homeworkUser/List'

TYPE_NAMES = {1: '单选题', 2: '多选题', 3: '判断题', 4: '填空题', 5: '问答题',
              6: '组合题', 9: '名词解释题', 10: '证明/计算/分析题',
              11: '翻译题', 12: '写作题', 13: '阅读理解题', 14: '其他题型'}
CHOICE_TYPES = {1, 3}
TEXT_TYPES = {5, 9, 10, 11, 12}


def emit(**payload):
    OUT.write(json.dumps(payload, ensure_ascii=False) + '\n')
    OUT.flush()


def log(text):
    emit(event='log', text=str(text))


def die(message):
    emit(event='error', message=str(message))
    raise SystemExit(1)


def read_state():
    if not STATE.exists():
        die('还没有登录状态，请先回界面点“读取课程”登录一次')
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except Exception as error:
        die(f'登录状态读不出来：{error}')


def uuid_of(state):
    for cookie in state.get('cookies', []):
        if cookie.get('name') == 'CASLOGC':
            try:
                return json.loads(unquote(cookie.get('value') or '')).get('uuid', '') or ''
            except Exception:
                return ''
    return ''


def ask():
    line = sys.stdin.readline()
    if not line:
        return {'action': 'skip'}
    try:
        return json.loads(line)
    except Exception:
        return {'action': 'skip'}


def open_browser(playwright, headless=True):
    context = playwright.chromium.launch_persistent_context(
        str(PROFILE), headless=headless, channel='msedge',
        service_workers='block', viewport={'width': 1440, 'height': 900})
    if STATE.exists():
        try:
            context.add_cookies(json.loads(STATE.read_text(encoding='utf-8')).get('cookies', []))
        except Exception:
            pass
    return context


def cmd_list(args):
    import run
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        context = open_browser(playwright, headless=not args.show)
        page = context.pages[0] if context.pages else context.new_page()
        client = run.Client(page)
        context.route('**/run/gateway/t/stu/**', client.route)
        page.goto(f'https://{run.HOST}/mySpace', wait_until='domcontentloaded', timeout=60000)
        smart = run.wait_login(context, client, args.timeout)
        flip = []
        try:
            flip = run.FlipClient(context).courses()
        except run.ApiError as error:
            log(f'翻转课列表读取失败：{error}')
        context.storage_state(path=str(STATE))
        emit(event='courses',
             smart=[{'id': c['course_id'], 'class_id': c['class_id'], 'name': c['name']}
                    for c in smart],
             flip=[{'id': c['course_id'], 'name': c['name']} for c in flip])
        context.close()


def clean_text(value):
    """题干和选项里带着 <p> 之类的标签，显示和喂给 AI 前先洗掉。"""
    text = re.sub(r'<[^>]+>', ' ', str(value or ''))
    text = html.unescape(text).replace('\xa0', ' ')
    return ' '.join(text.split())


def fetch_questions(context, homework_id, uuid):
    card = context.get(PAPER + '/getAnswerCard', params={
        'homeworkId': homework_id, 'uuid': uuid,
        'dateFormate': int(time.time() * 1000)}).json()
    if str(card.get('status')) != '200':
        die(f"答题卡接口返回 {card.get('status')}：{card.get('msg') or card.get('message')}")
    rt = card.get('rt') or {}
    rows = []
    for group in rt.get('groupDtoList') or []:
        for question in group.get('questionDtos') or []:
            rows.append(question)
    questions = []
    for index, row in enumerate(rows):
        question_id = str(row.get('questionId'))
        data = context.get(PAPER + '/getDoQuestSingle', params={
            'homeworkId': homework_id, 'questionId': question_id,
            'uuid': uuid, 'dateFormate': int(time.time() * 1000)}).json()
        item = data.get('rt') or {}
        options = []
        for option in item.get('questionOptionList') or []:
            try:
                sort = int(option.get('sort') or 0)
            except Exception:
                sort = 0
            options.append({'option_id': str(option.get('id')),
                            'letter': (chr(64 + sort) + '.') if sort else '',
                            'text': clean_text(option.get('content'))})
        options.sort(key=lambda option: option['letter'])
        view = item.get('homeworkUserPaperDoAnswerQuestViewDto') or {}
        existing = view.get('answer')
        if (existing is None or existing == '') and view.get('answerList'):
            existing = ','.join(str(value) for value in view['answerList'])
        type_id = item.get('questionTypeId')
        questions.append({
            'index': index,
            'question_id': question_id,
            'type_id': type_id,
            'type_name': TYPE_NAMES.get(type_id, f'题型{type_id}'),
            'content': clean_text(item.get('content')),
            'options': options,
            'existing_answer': existing,
            'done': bool(row.get('isDone')),
        })
    return questions


def build_answer_value(question, answer):
    """把 UI/AI 的答案转成接口要的 answer 字段。"""
    type_id = question.get('type_id')
    text = str(answer or '').strip()
    if not text:
        return None
    if type_id in CHOICE_TYPES:
        letters = [c for c in text.upper() if c.isalpha()]
        option = next((o for o in question['options']
                       if o['letter'].rstrip('.').upper() == letters[0]), None) if letters else None
        return option['option_id'] if option else None
    if type_id == 2:
        letters = [c for c in text.upper() if c.isalpha()]
        ids = [o['option_id'] for o in question['options']
               if o['letter'].rstrip('.').upper() in letters]
        return json.dumps(ids) if ids else None
    if type_id in TEXT_TYPES:
        return text
    return None


def cmd_homework(args):
    from playwright.sync_api import sync_playwright

    state = read_state()
    uuid = uuid_of(state)
    if not uuid:
        die('登录状态里没有 uuid，请先回界面点“读取课程”')
    with sync_playwright() as playwright:
        context = playwright.request.new_context(storage_state=str(STATE))
        data = context.get(LIST_API, params={
            'courseId': args.course, 'pageIndex': 1, 'pageSize': 50, 'key': '',
            'completeTab': 0, 'uuid': uuid,
            'dateFormate': int(time.time() * 1000)}).json()
        if str(data.get('status')) != '200':
            die(f"作业列表接口返回 {data.get('status')}：{data.get('msg') or data.get('message')}")
        items = ((data.get('rt') or {}).get('list')) or []
        emit(event='homework', course_id=args.course, items=[{
            'homework_id': str(item.get('homeworkId')),
            'title': item.get('title'),
            'status': item.get('status'),
            'score': item.get('homeworkScore'),
            'end_time': item.get('endTime'),
            'content': item.get('content') or '',
        } for item in items])
        context.dispose()


def cmd_answer(args):
    from playwright.sync_api import sync_playwright

    state = read_state()
    uuid = uuid_of(state)
    if not uuid:
        die('登录状态里没有 uuid，请先回界面点“读取课程”')
    with sync_playwright() as playwright:
        context = playwright.request.new_context(storage_state=str(STATE))
        questions = fetch_questions(context, args.homework, uuid)
        if not questions:
            die('没有抓到题目')
        emit(event='questions', course_id=args.course, homework_id=args.homework,
             title=args.title, questions=questions)
        emit(event='await')
        decision = ask()
        action = decision.get('action')
        if action not in ('save', 'submit'):
            emit(event='skipped', message='已取消，未做任何改动')
            context.dispose()
            return
        answers = {int(a.get('index', -1)): str(a.get('answer', ''))
                   for a in decision.get('answers') or []}
        saved = 0
        for question in questions:
            value = build_answer_value(question, answers.get(question['index'], ''))
            if value is None:
                log(f"第 {question['index'] + 1} 题（{question['type_name']}）没有可用答案，跳过")
                continue
            body = {'homeworkId': args.homework, 'questionId': question['question_id'],
                    'answer': value, 'pcFileJson': '[]', 'appFileJson': '',
                    'isSign': '0', 'uuid': uuid}
            result = context.post(PAPER + '/saveHomeworkAnswer', form=body).json()
            if str(result.get('status')) == '200' and result.get('rt') == 1:
                saved += 1
                log(f"第 {question['index'] + 1} 题已保存")
            else:
                log(f"第 {question['index'] + 1} 题保存失败：{result.get('msg') or result.get('message')}")
            time.sleep(0.25)
        if action == 'save':
            emit(event='saved', message=f'已保存 {saved}/{len(questions)} 题草稿（未提交）')
            context.dispose()
            return
        submit = context.post(PAPER + '/Submit', form={
            'homeworkId': args.homework, 'uuid': uuid}).json()
        if str(submit.get('status')) == '200':
            emit(event='submitted', message=f'已保存 {saved} 题并提交成功')
        else:
            emit(event='error',
                 message=f"提交失败：{submit.get('msg') or submit.get('message')}")
        context.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('list', 'homework', 'answer'))
    parser.add_argument('--course')
    parser.add_argument('--homework')
    parser.add_argument('--title')
    parser.add_argument('--show', action='store_true', help='列课程时显示浏览器窗口')
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args()
    if args.command == 'list':
        cmd_list(args)
    elif args.command == 'homework':
        if not args.course:
            die('homework 需要 --course')
        cmd_homework(args)
    else:
        if not (args.course and args.homework and args.title):
            die('answer 需要 --course/--homework/--title')
        cmd_answer(args)


if __name__ == '__main__':
    for stream in (OUT, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass
    main()