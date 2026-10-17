"""One privacy gate for database imports and public artifact generation."""
import re


def check_public(text):
    for pattern in [r'(?<![A-Za-z])[A-Za-z]:[\\/]', r'2026\.09[\\/]', r'2026\.10[\\/]',
                    r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', r'(?<!\d)1[3-9]\d{9}(?!\d)',
                    r'(?<!\d)\d{17}[\dXx](?!\d)', r'"sha256"', r'"review"']:
        for match in re.finditer(pattern, text):
            if '@' in pattern and match.group() == '2906725610@qq.com':
                continue
            raise ValueError('公开数据含本地路径、私人信息或内部资料，已停止导出')
    if '\ufffd' in text:
        raise ValueError('公开数据含损坏字符，已停止导出')
