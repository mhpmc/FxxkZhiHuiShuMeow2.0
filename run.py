import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

HOST = "ai-smart-course-student-pro.zhihuishu.com"
BASE = "https://kg-ai-run.zhihuishu.com/run/gateway/t/stu/"
FLIP_BASE = "https://hike-teaching.zhihuishu.com"
FLIP_COURSES = FLIP_BASE + "/educational/platform/getStudentCourseList"
FLIP_TREE = "https://studyresources.zhihuishu.com/studyResources/stuResouce/queryResourceTree"
FLIP_VIEW = "https://studyresources.zhihuishu.com/studyResources/stuResouce/stuViewFile"
FLIP_SAVE = FLIP_BASE + "/stuStudy/saveStuStudyRecord"
FLIP_SALT = "o6xpt3b#Qy$Z"
VIDEO_SUFFIXES = {'mp4', 'flv', 'avi', 'mov', 'mkv', 'wmv', 'm4v', 'rmvb', 'mpeg', 'rm', 'asf'}
DOCUMENT_SUFFIXES = {'doc', 'docx', 'pdf', 'ppt', 'pptx', 'xls', 'xlsx', 'txt',
                     'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'}
ROOT = Path(__file__).resolve().parent
READS = {"center/course-list", "knowledge-study/get-course-knowledge-dic",
         "resources/list-knowledge-resource", "resources/get-node-resources-detail",
         "studyRecord/get-knowledge-video-time", "class/is-end-study"}
WRITES = {"studyRecord/study", "studyRecord/report", "studyRecord/completed"}

BOOTSTRAP = r"""async () => {
    const src = [...document.querySelectorAll('script[type="module"][src]')]
        .map(s => s.src).find(s => {
            const u = new URL(s);
            return u.origin === location.origin && /\/assets\/index-[^/]+\.js$/.test(u.pathname);
        });
    if (!src) return false;
    const mod = await import(src);
    if (typeof mod.v !== 'function' || !String(mod.v).includes('.post(')) return false;
    window.__smartCourseRequest = mod.v;
    return true;
}"""
CALL = r"""async ({url, params}) => {
    let timer;
    try {
        return await Promise.race([
            window.__smartCourseRequest(url, {...params, dateFormate: Date.now()}),
            new Promise((_, reject) => {timer = setTimeout(() => reject(new Error()), 30000);})
        ]);
    } catch (_) { return {bridge_error: true}; }
    finally {clearTimeout(timer);}
}"""


class ApiError(RuntimeError):
    pass


class Client:
    def __init__(self, page):
        self.page = page
        self.active_write = None

    def route(self, route):
        relative = urlsplit(route.request.url).path.split('/run/gateway/t/stu/', 1)[-1]
        if relative in READS or relative == self.active_write:
            route.continue_()
        else:
            route.abort('blockedbyclient')

    def connect(self):
        return bool(self.page.evaluate(BOOTSTRAP))

    def call(self, path, params):
        if path not in READS | WRITES:
            raise ValueError('喵呜?Ծ‸Ծ 这个接口暂时不支持喵')
        self.active_write = path if path in WRITES else None
        try:
            result = self.page.evaluate(CALL, {'url': BASE + path, 'params': params})
        finally:
            self.active_write = None
        if not isinstance(result, dict) or result.get('bridge_error'):
            raise ApiError(f'喵?！(>﹏<) {path} 请求失败或超时啦；写入不会自动重试喵')
        code = result.get('code', result.get('status'))
        if str(code) != '200':
            raise ApiError(f'喵呜?Ծ‸Ծ {path} 返回业务码 {code}')
        return result.get('data')


class FlipClient:
    """Flipped-class resources live on wenda/hike, not on the smart-course host.

    They share the same login cookies. Only stuViewFile and
    saveStuStudyRecord write, so neither is ever retried here.
    """

    def __init__(self, context):
        self.context = context
        self.uuid = self._uuid()
        if not self.uuid:
            raise ApiError('喵…(ಥ_ಥ) 翻转课登录状态里没有学生 uuid，请重新登录喵')

    def _uuid(self):
        # CASLOGC is a URL-encoded JSON cookie; its uuid is what the save
        # endpoint checks. Without it the server answers "学生uuid不能为".
        for cookie in self.context.cookies():
            if cookie.get('name') != 'CASLOGC':
                continue
            try:
                return str(json.loads(unquote(cookie.get('value') or '')).get('uuid') or '')
            except (AttributeError, TypeError, ValueError):
                return ''
        return ''

    def get(self, url, params):
        try:
            response = self.context.request.get(url, params=params, timeout=30000)
        except Exception as error:
            raise ApiError(f'喵?！(>﹏<) 翻转课请求失败啦：{type(error).__name__}') from error
        if response.status != 200:
            raise ApiError(f'喵?！(>﹏<) 翻转课接口返回 HTTP {response.status}')
        try:
            data = response.json()
        except Exception as error:
            raise ApiError('喵呜?Ծ‸Ծ 翻转课返回的不是 JSON，页面结构可能变了') from error
        # These gateways report a string "200" for reads, a number 200 for
        # the course list; compare as text so both are accepted.
        if str(data.get('status')) != '200':
            raise ApiError(f'喵呜?Ծ‸Ծ 翻转课返回业务码 {data.get("status")}：'
                           f'{data.get("message") or ""}')
        return data

    def courses(self):
        data = self.get(FLIP_COURSES, {'year': '', 'term': '', 'uuid': self.uuid,
                                       'dateFormate': int(time.time() * 1000)})
        rt = data.get('rt')
        rows = rt.get('studyCourses') if isinstance(rt, dict) else None
        if not isinstance(rows, list):
            raise ApiError('喵?！(>﹏<) 翻转课课程列表结构变化啦，暂时不能确认已列出全部课程喵')
        found = {}
        for item in rows:
            course_id = str(item.get('courseId', ''))
            if not course_id.isdigit():
                raise ApiError('喵呜?Ծ‸Ծ 翻转课缺少有效课程 ID')
            found.setdefault(course_id, {'course_id': course_id,
                'name': str(item.get('courseName') or course_id), 'results': [], 'finished': False})
        return list(found.values())

    def tree(self, course_id):
        data = self.get(FLIP_TREE, {'courseId': course_id, 'uuid': self.uuid,
                                    'dateFormate': int(time.time() * 1000)})
        rows = []

        def walk(nodes):
            if not isinstance(nodes, list):
                return
            for item in nodes:
                if not isinstance(item, dict):
                    continue
                if str(item.get('type')) in {'1', '2'}:
                    rows.append(item)
                walk(item.get('childList') or [])

        walk(data.get('rt') or [])
        return rows


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else 0
    except (ValueError, TypeError):
        return 0


def flip_progress(study_time, total_time):
    # Same formula the wenda page uses for the ring/percentage.
    if not total_time:
        return 0
    value = math.floor(study_time * 1000 / total_time / 10)
    if value > 100:
        return 100
    return 1 if value == 0 and study_time > 0 else value


def flip_row(item):
    total_time = max(0, number(item.get('totalTime')))
    study_time = max(0, number(item.get('studyTime')))
    data_type = str(item.get('dataType') or '')
    name = str(item.get('name') or '')
    suffix = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if str(item.get('type')) == '2':
        kind = 'task'  # homework/test: has progress but is not a file
    elif data_type in {'3', '8'} or suffix in VIDEO_SUFFIXES:
        kind = 'video'
    elif data_type in {'1', '2', '5', '6'} or suffix in DOCUMENT_SUFFIXES:
        kind = 'document'  # opened and counted by stuViewFile
    else:
        kind = 'archive'  # zip/rar and other download-only files
    progress = flip_progress(study_time, total_time)
    return {'resource_id': str(item.get('id')), 'name': str(item.get('name') or item.get('id')),
            'kind': kind, 'data_type': data_type, 'must_learn': item.get('mustLearn'),
            'total_time': total_time, 'study_time': study_time,
            'progress': progress, 'completed': progress >= 80}


def flip_refresh(client, course_id, resource_id):
    for item in client.tree(course_id):
        if str(item.get('id')) == resource_id:
            return flip_row(item)
    raise ApiError('喵?！(>﹏<) 核验时翻转课资源从列表中消失啦')


def flip_save(client, course_id, row, start, delta):
    now = int(time.time() * 1000)
    end = int(start + delta)
    # The page's window.$md5 builds exactly this string; the server rejects
    # any other order or a missing uuid.
    text = (FLIP_SALT + client.uuid + course_id + row['resource_id'] + str(int(delta)) +
            str(now - int(delta) * 1000) + str(now) + str(end) + str(int(start)) + client.uuid)
    params = {'uuid': client.uuid, 'courseId': course_id, 'fileId': row['resource_id'],
              'studyTotalTime': int(delta), 'startWatchTime': int(start), 'endWatchTime': end,
              'startDate': now - int(delta) * 1000, 'endDate': now,
              'signature': hashlib.md5(text.encode('utf-8')).hexdigest(), '_': now}
    data = client.get(FLIP_SAVE, params)
    return max(0, number(data.get('rt')))


def process_flip(client, course, row, interval, checkpoint):
    if row['kind'] == 'task':
        return row, 'skipped_task'
    if row.get('must_learn') == 0:
        return row, 'skipped_optional'
    if row['completed']:
        return row, 'already_completed'
    if row['kind'] == 'archive':
        # stuViewFile does not move these from 0/1; the page only offers a
        # download link, so their completion rule cannot be confirmed here.
        return row, 'skipped_archive'
    course_id = course['course_id']
    if row['kind'] == 'document':
        # Opening the document page calls the same endpoint and flips 0/1 to
        # 1/1 without any signature or player.
        client.get(FLIP_VIEW, {'courseId': course_id, 'fileId': row['resource_id'],
                               '_': int(time.time() * 1000)})
        time.sleep(interval)
        after = flip_refresh(client, course_id, row['resource_id'])
        for _ in range(2):
            if after['completed']:
                break
            time.sleep(2)
            after = flip_refresh(client, course_id, row['resource_id'])
        return after, 'completed' if after['completed'] else 'not_confirmed'
    if not row['total_time']:
        return row, 'missing_duration'
    # Learn the whole video in 30-second batches, like the native player.
    position = int(row['study_time'])
    total = int(row['total_time'])
    batch = 0
    observed = row
    while position < total:
        delta = max(1, int(min(30, total - position)))
        batch += 1
        saved = flip_save(client, course_id, row, position, delta)
        time.sleep(interval)
        if saved <= position:
            # Read delay: give the server one delayed chance before stopping.
            time.sleep(2)
            observed = flip_refresh(client, course_id, row['resource_id'])
            if observed['study_time'] <= position:
                checkpoint({'position': position, 'batch': batch, 'observed': observed})
                break
            position = int(observed['study_time'])
        else:
            position = int(saved)
        if batch % 5 == 0 or position >= total:
            observed = flip_refresh(client, course_id, row['resource_id'])
            checkpoint({'position': position, 'batch': batch, 'observed': observed})
            print(f"    喵(●—●) 翻转课已记录 {observed['study_time']:g}/{total:g} 秒，"
                  f"进度 {observed['progress']:g}%，完成标记 {observed['completed']}", flush=True)
            if observed['completed']:
                return observed, 'completed'
            position = max(position, int(observed['study_time']))
    after = flip_refresh(client, course_id, row['resource_id'])
    return after, 'completed' if after['completed'] else 'not_confirmed'


def flip_course_ids(values):
    result = []
    for value in values:
        value = value.strip()
        if value.isdigit():
            result.append(value)
            continue
        found = parse_qs(urlsplit(value).query).get('courseId')
        if not found or not found[0].isdigit():
            raise ValueError(value)
        result.append(found[0])
    return result


def course_list(data):
    if not isinstance(data, dict) or not all(isinstance(data.get(k), list)
            for k in ('studyCourseList', 'completeCourseList')):
        raise ApiError('喵?！(>﹏<) 课程列表结构变化啦，暂时不能确认已列出全部课程喵')
    found = {}
    for item in data['studyCourseList'] + data['completeCourseList']:
        # These are the types the native page opens as smart-course routes.
        if str(item.get('courseType')) not in {'0', '1'} or not item.get('newFlag'):
            continue
        course_id, class_id = str(item.get('courseId', '')), str(item.get('classId', ''))
        if not course_id.isdigit() or not class_id.isdigit():
            raise ApiError('喵呜?Ծ‸Ծ 智慧课程缺少有效课程或班级 ID')
        found.setdefault((course_id, class_id), {'course_id': course_id, 'class_id': class_id,
            'name': str(item.get('courseName') or course_id), 'results': [], 'finished': False})
    return list(found.values())


def catalog_nodes(data):
    nodes = {}
    def walk(value):
        if isinstance(value, dict):
            uid = str(value.get('knowledgeId', ''))
            if uid.isdigit():
                nodes.setdefault(uid, str(value.get('knowledgeName') or uid))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(data)
    return nodes


def params(course, node=None):
    result = {'courseId': course['course_id'], 'classId': course['class_id']}
    if node:
        result['knowledgeId'] = node
    return result


def resources(client, course, node):
    data = client.call('resources/list-knowledge-resource', params(course, node))
    if not isinstance(data, dict) or not isinstance(data.get('resourceList'), list):
        raise ApiError('喵呜?Ծ‸Ծ 组件列表结构变化啦')
    rows = []
    for item in data['resourceList']:
        detail = item.get('resourcesDetail') or {}
        uid = str(detail.get('resourcesUid') or '')
        if not uid.isdigit():
            raise ApiError('喵呜?Ծ‸Ծ 组件缺少有效资源 ID')
        suffix = str(detail.get('resourcesSuffix') or '').lower().lstrip('.')
        video = suffix == 'mp4' or str(detail.get('resourcesDataType')) == '22'
        # Native learnPage groups resourcesSyncType == 1 as required and
        # other values as optional. Missing metadata stays eligible for work.
        sync_type = detail.get('resourcesSyncType')
        optional = sync_type is not None and number(sync_type) != 1
        rows.append({'node_id': node, 'resource_id': uid,
                     'name': str(detail.get('resourcesName') or uid),
                     'kind': 'video' if video else 'document',
                     'file_id': str(detail.get('resourcesFileId') or ''),
                     'duration': max(0, math.ceil(number(detail.get('resourcesTime')))),
                     'study_seconds': number(item.get('studyTotalTime')),
                     'schedule': number(item.get('schedule')),
                     'optional': optional,
                     'completed': str(item.get('studyStatus')) == '1'})
    return rows


def refresh(client, course, row):
    for candidate in resources(client, course, row['node_id']):
        if candidate['resource_id'] == row['resource_id']:
            return candidate
    raise ApiError('喵?！(>﹏<) 核验时目标组件从列表中消失啦')


def mark_completed(client, course, row, interval, document=False):
    if row.get('optional') or row['completed']:
        return row
    client.call('studyRecord/completed', {**params(course, row['node_id']),
                'resourcesUid': row['resource_id'], 'watchUId': 1})
    if document:
        client.call('studyRecord/study', {**params(course, row['node_id']),
                    'resourceId': row['resource_id'], 'source': 1, 'studyFileType': 2})
    client.page.wait_for_timeout(interval * 1000)
    after = refresh(client, course, row)
    for _ in range(2):
        if after['completed']:
            break
        client.page.wait_for_timeout(2000)
        after = refresh(client, course, row)
    return after


def process(client, course, row, interval, checkpoint):
    if row.get('optional'):
        return row, 'skipped_optional'
    if row['completed']:
        return row, 'already_completed'
    # The node list may have been read before earlier components were processed.
    # Recheck pending entries so a newly completed resource receives no writes.
    row = refresh(client, course, row)
    if row.get('optional'):
        return row, 'skipped_optional'
    if row['completed']:
        return row, 'already_completed'
    if row['kind'] != 'video':
        after = mark_completed(client, course, row, interval, document=True)
        return after, 'completed' if after['completed'] else 'not_confirmed'

    detail = client.call('resources/get-node-resources-detail', {
        **params(course, row['node_id']), 'resourcesUid': row['resource_id']})
    if not isinstance(detail, dict):
        raise ApiError('喵呜?Ծ‸Ծ 视频详情结构变化啦')
    nested = detail.get('resourcesDetail') or {}
    file_id = str(detail.get('resourcesFileId') or nested.get('resourcesFileId') or row['file_id'])
    duration = row['duration'] or max(0, math.ceil(number(nested.get('resourcesTime'))))
    if not duration or not file_id.isdigit() or int(file_id) > 2**53 - 1:
        after = mark_completed(client, course, row, interval)
        return after, 'completed_without_video_time' if after['completed'] else 'missing_video_metadata'
    # Every unfinished video starts a fresh position sequence from zero.
    # Preserve the server's accumulated time; do not reset its learning record.
    position = 0
    already_recorded = row['study_seconds']
    observed = row
    batch = 0
    previous_time = row['study_seconds']
    while position < duration:
        delta = min(10, duration - position)
        position += delta
        batch += 1
        client.call('studyRecord/study', {**params(course, row['node_id']),
            'resourceId': row['resource_id'], 'source': 1, 'studyFileType': 1,
            'fileId': int(file_id), 'studyTime': delta, 'lastWatchTime': int(position)})
        client.call('studyRecord/report', {**params(course, row['node_id']),
            'fileId': int(file_id), 'studyTotalTime': delta, 'lastWatchTime': int(position),
            'shareCourseId': '', 'watchUId': 1, 'nodeType': 1})
        client.page.wait_for_timeout(interval * 1000)
        if batch % 5 == 0 or position >= duration:
            observed = refresh(client, course, row)
            checkpoint({'position': position, 'batch': batch, 'observed': observed})
            print(f"    喵(●—●) 已记录 {observed['study_seconds']:g}/{duration} 秒，"
                  f"进度 {observed['schedule']:g}%，完成标记 {observed['completed']}", flush=True)
            if observed.get('optional'):
                return observed, 'skipped_optional'
            if observed['completed']:
                return observed, 'completed'
            if position > already_recorded and observed['study_seconds'] <= previous_time:
                # Check read delay before sending the final completion report.
                for _ in range(2):
                    client.page.wait_for_timeout(2000)
                    observed = refresh(client, course, row)
                    if observed.get('optional'):
                        return observed, 'skipped_optional'
                    if observed['completed'] or observed['study_seconds'] > previous_time:
                        break
                checkpoint({'position': position, 'batch': batch, 'observed': observed})
                if observed['completed']:
                    return observed, 'completed'
                if observed['study_seconds'] <= previous_time:
                    break
            previous_time = observed['study_seconds']
    after = mark_completed(client, course, observed, interval)
    return after, 'completed' if after['completed'] else 'not_confirmed'


def wait_login(context, client, timeout):
    deadline = time.monotonic() + timeout
    print('喵(๑°3°๑) 请在打开的浏览器中登录呀～登录后本喵会自动开始，不用按回车或打开 F12 喵！', flush=True)
    while time.monotonic() < deadline:
        pages = [p for p in context.pages if not p.is_closed()]
        if not pages:
            raise ApiError('喵…(ಥ_ಥ) 浏览器窗口被关掉啦，请重新启动脚本喵')
        for page in reversed(pages):
            if urlsplit(page.url).hostname != HOST:
                continue
            client.page = page
            try:
                if client.connect():
                    data = client.call('center/course-list', {})
                    return course_list(data)
            except ApiError as error:
                # Authentication errors during login are expected; schema
                # errors on a successful list are not silently retried.
                if '结构' in str(error) or '缺少' in str(error):
                    raise
            except Exception:
                pass  # Login navigation can replace the JavaScript context.
        pages[-1].wait_for_timeout(1000)
    raise ApiError('喵呜?Ծ‸Ծ 等待登录超时啦，请重新启动，再陪本喵登录一次吧')


def run(args):
    from playwright.sync_api import sync_playwright
    profile = ROOT / '.session'
    output = ROOT / 'output'
    output.mkdir(parents=True, exist_ok=True)
    target = output / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'courses': [],
              'flip_courses': [], 'finished': False}
    def save():
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        # Windows can briefly deny the replace while a scanner holds the new
        # file; this is a local report, so a short retry is safe.
        for attempt in range(3):
            try:
                temp.replace(target)
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.2)
    save()
    try:
        with sync_playwright() as playwright:
            options = {'headless': False, 'service_workers': 'block'}
            if args.channel != 'chromium':
                options['channel'] = args.channel
            context = playwright.chromium.launch_persistent_context(str(profile), **options)
            try:
                state_file = profile / 'auth-state.json'
                if args.fresh_login:
                    context.clear_cookies()
                elif state_file.exists():
                    try:
                        context.add_cookies(json.loads(state_file.read_text(encoding='utf-8')).get('cookies', []))
                    except Exception:
                        print('喵…(ಥ_ಥ) 旧登录状态没能恢复，请重新登录一下喵～')
                page = context.pages[0] if context.pages else context.new_page()
                client = Client(page)
                context.route('**/run/gateway/t/stu/**', client.route)
                page.goto(f'https://{HOST}/mySpace', wait_until='domcontentloaded', timeout=60000)
                courses = wait_login(context, client, args.login_timeout)
                context.storage_state(path=str(state_file))
                if args.no_smart:
                    courses = []
                elif args.course:
                    wanted = set(args.course)
                    courses = [c for c in courses if c['course_id'] in wanted]
                report['courses'] = courses
                save()
                print(f'喵~(๑＞ڡ＜)☆ 找到 {len(courses)} 门智慧课程啦！', flush=True)
                for course in courses:
                    print(f"喵喵喵！(づ ●─● )づ 开始处理课程：{course['name']}", flush=True)
                    try:
                        client.page.goto(f"https://{HOST}/singleCourse/knowledgeStudy/"
                                         f"{course['course_id']}/{course['class_id']}",
                                         wait_until='domcontentloaded', timeout=60000)
                        if not client.connect():
                            raise ApiError('喵呜?Ծ‸Ծ 网页请求模块没找到，或版本已经变化啦')
                        nodes = catalog_nodes(client.call('knowledge-study/get-course-knowledge-dic', params(course)))
                        if not nodes:
                            raise ApiError('喵?！(>﹏<) 没读到知识点目录，暂时不能确认课程完成喵')
                        course['node_count'] = len(nodes)
                        for node, name in nodes.items():
                            print(f'  喵(๑• . •๑) 当前知识点：{name}', flush=True)
                            for row in resources(client, course, node):
                                entry = {'before': row, 'outcome': 'pending', 'checkpoints': []}
                                course['results'].append(entry)
                                save()
                                print(f"  喵～看看这条小鱼干：{row['name']}", flush=True)
                                def checkpoint(value):
                                    entry['checkpoints'].append(value)
                                    save()
                                try:
                                    after, outcome = process(client, course, row, args.interval, checkpoint)
                                    entry.update(after=after, outcome=outcome)
                                    if outcome == 'already_completed':
                                        print('    喵~(๑＞ڡ＜)☆ 已经完成啦，直接跳过，省点时间喵！', flush=True)
                                    elif outcome == 'skipped_optional':
                                        print('    喵(๑°3°๑) 这是选学资源，不要求学，跳过喵～', flush=True)
                                except ApiError as error:
                                    entry.update(outcome='error', error=str(error))
                                    print(f'    喵…(ಥ_ಥ) 这个组件还没完成：{error}，先继续下一个喵～', flush=True)
                                save()
                        # Re-read each node so final counts reflect server state.
                        final = [r for node in nodes for r in resources(client, course, node)]
                        course['final_components'] = final
                        course['component_count'] = len(final)
                        course['completed_count'] = sum(r['completed'] for r in final)
                        required = [r for r in final if not r['optional']]
                        course['required_count'] = len(required)
                        course['completed_required_count'] = sum(r['completed'] for r in required)
                        course['skipped_optional_count'] = sum(r['optional'] for r in final)
                        course['skipped_completed_count'] = sum(
                            entry['outcome'] == 'already_completed' for entry in course['results'])
                        course['finished'] = True
                        print(f"喵(●—●) 课程核验结果：{course['completed_required_count']}/{len(required)} 个必学组件已完成，"
                              f"跳过选学资源 {course['skipped_optional_count']} 个喵～", flush=True)
                    except ApiError as error:
                        course['error'] = str(error)
                        print(f'喵…(ಥ_ಥ) 这门课还没处理完：{error}，先继续下一门喵～', flush=True)
                    save()
                if not args.no_flip:
                    flip_client = None
                    try:
                        flip_client = FlipClient(context)
                        flip_courses = flip_client.courses()
                        if args.flip_course:
                            wanted = set(args.flip_course)
                            flip_courses = [c for c in flip_courses if c['course_id'] in wanted]
                        print(f'喵(●—●) 翻转课找到 {len(flip_courses)} 门要看看的课程喵～', flush=True)
                    except ApiError as error:
                        report['flip_error'] = str(error)
                        flip_courses = []
                        print(f'喵…(ಥ_ಥ) 翻转课没能开始：{error}', flush=True)
                    for flip_course in flip_courses:
                        entry = {'course_id': flip_course['course_id'], 'name': flip_course['name'],
                                 'results': [], 'finished': False}
                        report['flip_courses'].append(entry)
                        save()
                        print(f"喵喵喵！(づ ●─● )づ 开始处理翻转课：{entry['name']}", flush=True)
                        try:
                            rows = [flip_row(item) for item in flip_client.tree(entry['course_id'])]
                            for row in rows:
                                item = {'before': row, 'outcome': 'pending', 'checkpoints': []}
                                entry['results'].append(item)
                                save()
                                print(f"  喵～看看这条小鱼干：{row['name']}", flush=True)

                                def checkpoint(value, item=item):
                                    item['checkpoints'].append(value)
                                    save()

                                try:
                                    after, outcome = process_flip(flip_client, entry, row,
                                                                  args.interval, checkpoint)
                                    item.update(after=after, outcome=outcome)
                                    if outcome == 'already_completed':
                                        print('    喵~(๑＞ڡ＜)☆ 已经完成啦，直接跳过，省点时间喵！', flush=True)
                                    elif outcome == 'skipped_optional':
                                        print('    喵(๑°3°๑) 这是选学资源，不要求学，跳过喵～', flush=True)
                                    elif outcome == 'skipped_task':
                                        print('    喵(๑°3°๑) 这是作业/测验，本喵不会替你作答，跳过喵～', flush=True)
                                    elif outcome == 'skipped_archive':
                                        print('    喵(๑°3°๑) 这是压缩包，网页只提供下载，本喵不猜它的完成方式，跳过喵～', flush=True)
                                except ApiError as error:
                                    item.update(outcome='error', error=str(error))
                                    print(f'    喵…(ಥ_ಥ) 这个翻转课资源还没完成：{error}，先继续下一个喵～', flush=True)
                                save()
                            final = [flip_row(item) for item in flip_client.tree(entry['course_id'])]
                            entry['final_resources'] = final
                            entry['resource_count'] = len(final)
                            required = [r for r in final
                                        if r['kind'] != 'task' and r.get('must_learn') != 0]
                            entry['required_count'] = len(required)
                            entry['completed_required_count'] = sum(r['completed'] for r in required)
                            entry['skipped_task_count'] = sum(r['kind'] == 'task' for r in final)
                            entry['skipped_optional_count'] = sum(
                                r['kind'] != 'task' and r.get('must_learn') == 0 for r in final)
                            entry['finished'] = True
                            print(f"喵(●—●) 翻转课核验结果：{entry['completed_required_count']}/{len(required)} "
                                  f"个必学资源已完成，跳过作业/测验 {entry['skipped_task_count']} 个喵～", flush=True)
                        except ApiError as error:
                            entry['error'] = str(error)
                            print(f'喵…(ಥ_ಥ) 这门翻转课还没处理完：{error}，先继续下一门喵～', flush=True)
                        save()
                report['finished'] = True
                save()
            finally:
                context.close()
    except (KeyboardInterrupt, Exception) as error:
        report['error'] = str(error) if isinstance(error, ApiError) else type(error).__name__
        save()
        print(f"喵…(ಥ_ಥ) 本次运行已停止：{report['error']}。结果已经保存到：{target}\n"
              '给本喵一点小鱼干干，准备好后再重新启动吧喵！(/≧▽≦/)')
        return 1
    unresolved = sum(c.get('required_count', 0) - c.get('completed_required_count', 0)
                     for c in report['courses'])
    unresolved_flip = sum(c.get('required_count', 0) - c.get('completed_required_count', 0)
                          for c in report.get('flip_courses', []))
    failures = (sum(bool(c.get('error')) for c in report['courses']) +
                sum(bool(c.get('error')) for c in report.get('flip_courses', [])) +
                bool(report.get('flip_error')))
    mood = '喵…(ಥ_ಥ)' if unresolved or unresolved_flip or failures else '喵~！⊙▽⊙→✪ω✪→(/≧▽≦/)'
    print(f'{mood} 全部课程已遍历完啦！未完成必学组件 {unresolved} 个，'
          f'翻转课未完成必学资源 {unresolved_flip} 个，未处理完课程 {failures} 门。\n'
          f'结果保存在：{target}')
    return 2 if unresolved or unresolved_flip or failures else 0


def main():
    # Keep the supplied kaomoji printable on Windows and in redirected logs.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='喵~(๑＞ڡ＜)☆ 登录后自动吃掉账号下全部小鱼干')
    parser.add_argument('--interval', type=float, default=1, help='上报批次间隔秒数，默认 1 秒喵')
    parser.add_argument('--channel', choices=('msedge', 'chrome', 'chromium'), default='msedge',
                        help='选择浏览器，默认 Edge 喵')
    parser.add_argument('--login-timeout', type=int, default=1800, help='等待登录秒数，默认 1800 秒喵')
    parser.add_argument('--fresh-login', action='store_true', help='重新登录，更换学生账号时用这个喵')
    parser.add_argument('--no-flip', action='store_true', help='跳过翻转课，只刷智慧课程喵')
    parser.add_argument('--flip-course', action='append', default=[], metavar='ID或URL',
                        help='只处理指定翻转课（课程 ID 或 studyResource 网址），可重复喵')
    parser.add_argument('--no-smart', action='store_true', help='跳过智慧课程，只处理翻转课喵')
    parser.add_argument('--course', action='append', default=[], metavar='ID',
                        help='只处理指定智慧课程 ID，可重复喵')
    args = parser.parse_args()
    if not math.isfinite(args.interval) or not 0.5 <= args.interval <= 60:
        parser.error('喵?！(>﹏<) --interval 必须为 0.5 到 60 秒喵')
    if not 30 <= args.login_timeout <= 7200:
        parser.error('喵?！(>﹏<) --login-timeout 必须为 30 到 7200 秒喵')
    if any(not value.isdigit() for value in args.course):
        parser.error('喵?！(>﹏<) --course 需要纯数字的智慧课程 ID 喵')
    try:
        args.flip_course = flip_course_ids(args.flip_course)
    except ValueError:
        parser.error('喵?！(>﹏<) --flip-course 需要翻转课 ID，或带 courseId 的网址喵')
    print('喵呜！(ﾉ ○ Д ○)ﾉ 智慧课程/翻转课小助手上线啦～\n'
          '本喵只有九条命，运行时请保持浏览器窗口打开，温柔地陪本喵工作喵(๑• . •๑)', flush=True)
    try:
        return run(args)
    except ImportError:
        print('喵?！(>﹏<) 还缺少依赖呀～请先运行：\n'
              'python -m pip install -r script/requirements.txt\n'
              '装好后再来找本喵玩吧！(/≧▽≦/)')
        return 1

if __name__ == '__main__':
    sys.exit(main())
