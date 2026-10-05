"""보드에 원천 문서의 안전한 읽기 전용 HTML을 담는다. 파일·HTTP 환경에서 fetch 없이 열람한다."""
from html import escape
import re
from urllib.parse import urlsplit

from deliverables import split
from jev_observe import local_file

INLINE = re.compile(r'`([^`]+)`|(?<!!)\[([^\]]+)\]\(([^\s)]+)\)|\*\*([^*]+)\*\*|\*([^*]+)\*')
BLOCK = re.compile(r'^(#{1,6}\s|```|~~~|[-*+]\s|\d+\.\s|>\s|\|)')


def inline(text):
    parts, end = [], 0
    for match in INLINE.finditer(text):
        parts.append(escape(text[end:match.start()]))
        code, label, url, strong, emphasis = match.groups()
        if code is not None:
            parts.append(f'<code>{escape(code)}</code>')
        elif label is not None:
            try:
                safe_url = urlsplit(url).scheme.lower() in ('http', 'https')
            except ValueError:
                safe_url = False
            if safe_url:
                parts.append(f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>')
            else:
                parts.append(escape(match.group()))
        else:
            tag, value = ('strong', strong) if strong is not None else ('em', emphasis)
            parts.append(f'<{tag}>{escape(value)}</{tag}>')
        end = match.end()
    return ''.join(parts) + escape(text[end:])


def markdown(text):
    # ponytail: 기본 Markdown 블록만 렌더링한다. 수식·Mermaid는 원문을 보존하며, 전체 CommonMark가 필요하면 검증된 파서로 교체한다.
    lines, blocks, i = text.splitlines(), [], 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        fence = re.match(r'^(`{3,}|~{3,})', line)
        if fence:
            marker, code, i = fence.group(), [], i + 1
            while i < len(lines) and not re.fullmatch(re.escape(marker[0]) + '{' + str(len(marker)) + ',}', lines[i].strip()):
                code.append(lines[i])
                i += 1
            blocks.append('<pre><code>' + escape('\n'.join(code)) + '</code></pre>')
        elif re.match(r'^#{1,6}\s', line):
            level, title = re.match(r'^(#{1,6})\s+(.*)', line).groups()
            blocks.append(f'<h{len(level)}>{inline(title)}</h{len(level)}>')
        elif line.startswith('|') and i + 1 < len(lines) and re.fullmatch(r'[\s|:-]+', lines[i + 1]) and '-' in lines[i + 1]:
            def row(raw, tag):
                return '<tr>' + ''.join(f'<{tag}>{inline(c.strip())}</{tag}>' for c in raw.strip().strip('|').split('|')) + '</tr>'
            table, i = ['<div class="scroll"><table><thead>', row(line, 'th'), '</thead><tbody>'], i + 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                table.append(row(lines[i], 'td'))
                i += 1
            blocks.append(''.join(table) + '</tbody></table></div>')
            continue
        elif re.match(r'^([-*+]\s|\d+\.\s)', line):
            ordered = bool(re.match(r'^\d+\.', line))
            tag, items = ('ol' if ordered else 'ul'), []
            pattern = r'^\d+\.\s+(.*)' if ordered else r'^[-*+]\s+(.*)'
            while i < len(lines) and (item := re.match(pattern, lines[i].strip())):
                items.append('<li>' + inline(item[1]) + '</li>')
                i += 1
            blocks.append(f'<{tag}>' + ''.join(items) + f'</{tag}>')
            continue
        elif line.startswith('>'):
            blocks.append('<blockquote>' + inline(line.lstrip('> ').strip()) + '</blockquote>')
        elif re.fullmatch(r'(?:-{3,}|\*{3,}|_{3,})', line):
            blocks.append('<hr>')
        else:
            paragraph, i = [line], i + 1
            while i < len(lines) and lines[i].strip() and not BLOCK.match(lines[i].strip()):
                paragraph.append(lines[i].strip())
                i += 1
            blocks.append('<p>' + '<br>'.join(inline(p) for p in paragraph) + '</p>')
            continue
        i += 1
    return '\n'.join(blocks)


def documents(root, sources):
    root, result, seen = root.resolve(), [], set()
    for source in sources:
        name = source
        path = root / name
        try:
            if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in (path, *path.parents) if p != root and p.is_relative_to(root)):
                raise ValueError('unsafe source')
            files = sorted(path.rglob('*.md')) if path.is_dir() else [path]
        except (OSError, ValueError):
            result.append({'path': name, 'title': name, 'state': 'blocked', 'exists': False})
            continue
        for file in files or [path]:
            relative = file.relative_to(root).as_posix()
            if relative in seen:
                continue
            seen.add(relative)
            entry = {'path': relative, 'title': file.name, 'state': 'missing', 'exists': file.is_file()}
            try:
                if not entry['exists']:
                    entry['state'] = 'unwritten' if file.is_dir() else 'missing'
                else:
                    file = local_file(root, relative)
                    text = file.read_text(encoding='utf-8')
                    if '\0' in text:
                        raise UnicodeError('binary document')
                    meta, body = split(text)
                    entry['meta'] = meta or {}
                    title = (meta or {}).get('title') or next((l[2:].strip() for l in body.splitlines() if l.startswith('# ')), file.name)
                    entry.update(title=str(title), state='available' if body.strip() else 'unwritten')
                    entry['html'] = markdown(body) if file.suffix.lower() == '.md' else '<pre>' + escape(body) + '</pre>'
            except (OSError, UnicodeError):
                entry['state'] = 'unreadable'
            except ValueError:
                entry.update(state='blocked', exists=False)
            result.append(entry)
    return result
