"""DeepSeek 官方 API 客户端 + 本地配置读写。

只用标准库 urllib，不引入额外依赖。
API Key 存在 script/config.json，打包发送前请删掉该文件。
"""
import json
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / 'config.json'
DEFAULT_BASE = 'https://api.deepseek.com'
DEFAULT_MODEL = 'deepseek-chat'


class AiError(RuntimeError):
    pass


def load_config():
    if not CONFIG.exists():
        return {}
    try:
        data = json.loads(CONFIG.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_config(data):
    merged = load_config()
    merged.update(data)
    CONFIG.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')
    return merged


class DeepSeek:
    def __init__(self, api_key, base_url=DEFAULT_BASE, model=DEFAULT_MODEL, timeout=180):
        self.api_key = (api_key or '').strip()
        if not self.api_key:
            raise AiError('喵…还没有填 DeepSeek API Key 喵')
        self.base_url = (base_url or DEFAULT_BASE).strip().rstrip('/')
        self.model = (model or DEFAULT_MODEL).strip()
        self.timeout = timeout

    def chat(self, messages, temperature=0.2, json_mode=False):
        payload = {'model': self.model, 'messages': messages,
                   'temperature': temperature, 'stream': False}
        if json_mode:
            payload['response_format'] = {'type': 'json_object'}
        request = urllib.request.Request(
            self.base_url + '/chat/completions',
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json',
                     'Authorization': 'Bearer ' + self.api_key},
            method='POST')
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as error:
            detail = error.read().decode('utf-8', 'replace')[:300]
            raise AiError(f'喵…DeepSeek 返回 HTTP {error.code}：{detail}') from error
        except Exception as error:
            raise AiError(f'喵…DeepSeek 请求失败：{type(error).__name__}') from error
        try:
            return data['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as error:
            raise AiError('喵…DeepSeek 返回结构看不懂喵') from error

    def test(self):
        return self.chat([{'role': 'user', 'content': '回复两个字：可用'}], temperature=0)

    def answer_questions(self, questions, course_hint='', temperature=0.2):
        """questions: [{id, type, stem, options}] -> [{id, answer, confidence, reason}]"""
        system = (
            '你是一名严谨的答题助手。只根据题目本身作答，不要编造题外内容。'
            '必须只输出 JSON，格式为 {"answers":[{"id":"题号","answer":"答案",'
            '"confidence":0.0,"reason":"简要理由"}]}。'
            '选择题 answer 用选项字母（多选按顺序连写，例如 "AC"）；'
            '判断题 answer 用 "对" 或 "错"；填空、简答直接给文字。'
            'confidence 用 0 到 1 之间的小数表示把握程度。')
        user = json.dumps({'course': course_hint, 'questions': questions},
                          ensure_ascii=False)
        content = self.chat([{'role': 'system', 'content': system},
                             {'role': 'user', 'content': user}],
                            temperature=temperature, json_mode=True)
        try:
            data = json.loads(content)
        except Exception as error:
            raise AiError('喵…DeepSeek 没有按要求返回 JSON 喵') from error
        answers = data.get('answers')
        if not isinstance(answers, list):
            raise AiError('喵…DeepSeek 返回的 answers 不是列表喵')
        return answers


if __name__ == '__main__':
    import sys
    config = load_config()
    key = config.get('deepseek_api_key', '')
    if not key:
        print('config.json 里还没有 deepseek_api_key')
        sys.exit(1)
    client = DeepSeek(key, config.get('base_url', DEFAULT_BASE),
                      config.get('model', DEFAULT_MODEL))
    print(client.test())