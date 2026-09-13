import re
import html
import time
import sys
import os

try:
    import translators as ts
except ImportError:
    print("Ошибка: библиотека 'translators' не установлена. Установите: pip install translators")
    sys.exit(1)

T_PATTERN = re.compile(r"<t\s+name=['\"]([^'\"]+)['\"]>(.*?)</t>", re.DOTALL)

TRANSLATORS = ['bing', 'alibaba', 'yandex', 'google']

PLACEHOLDER_PATTERNS = [
    (re.compile(r'%[0-9]*\$?[sd]'), 'percent'),
    (re.compile(r'\{[0-9]+\}'), 'brace'),
    (re.compile(r'\\n'), 'newline'),
    (re.compile(r'\\t'), 'tab'),
    (re.compile(r'\[[A-Z]+\]'), 'bracket'),
    (re.compile(r'<[^>]+>'), 'angle'),
]

TOKEN_PREFIX = '@@'
TOKEN_SUFFIX = '@@'


def read_xml_keys(filepath):
    with open(filepath, 'r', encoding='utf-8', newline='') as f:
        content = f.read()
    keys = {}
    for match in T_PATTERN.finditer(content):
        key = match.group(1)
        value = html.unescape(match.group(2))
        keys[key] = value
    return keys


def extract_root_tag(content):
    root_open_match = re.search(r'<\?xml[^>]*\?>\s*(<[^>]+>)', content, re.DOTALL)
    if not root_open_match:
        raise ValueError("Не найден корневой тег")
    root_open = root_open_match.group(1)
    tag_match = re.match(r'<(\w+)', root_open)
    if not tag_match:
        raise ValueError("Не удалось определить имя корневого тега")
    root_name = tag_match.group(1)
    root_close = f'</{root_name}>'
    return root_open, root_close


def protect_placeholders(text):
    protected = []
    token_map = {}
    token_counter = [0]

    def replace_match(match, ptype):
        token = f'{TOKEN_PREFIX}{token_counter[0]}{TOKEN_SUFFIX}'
        token_counter[0] += 1
        token_map[token] = match.group(0)
        protected.append((token, match.group(0)))
        return token

    result = text
    for pattern, ptype in PLACEHOLDER_PATTERNS:
        def repl(m):
            return replace_match(m, ptype)
        result = pattern.sub(repl, result)
    return result, token_map


def restore_placeholders(text, token_map):
    result = text
    for token, original in token_map.items():
        result = result.replace(token, original)
    for token, original in token_map.items():
        num = token[len(TOKEN_PREFIX):-len(TOKEN_SUFFIX)]
        fuzzy_variants = [
            f'{TOKEN_PREFIX} {num} {TOKEN_SUFFIX}',
            f'{TOKEN_PREFIX}{num} {TOKEN_SUFFIX}',
            f'{TOKEN_PREFIX} {num}{TOKEN_SUFFIX}',
            f'@{num}@',
            f'@ {num} @',
        ]
        for variant in fuzzy_variants:
            result = result.replace(variant, original)
    return result


def translate_text(text, src='en', dest='ru'):
    if not text or not text.strip():
        return text

    protected_text, token_map = protect_placeholders(text)

    leading = text[:len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()):]
    core = text.strip()

    translated_core = None
    for service in TRANSLATORS:
        for attempt in range(3):
            try:
                print(f'  ({service}) попытка {attempt+1}/3...')
                translated_core = ts.translate_text(core, translator=service, from_language=src, to_language=dest)
                if translated_core and translated_core.strip():
                    print(f'  ({service}) перевод успешен: {repr(translated_core[:50])}...')
                    break
                else:
                    print(f'  ({service}) пустой результат')
            except Exception as e:
                print(f'  ({service}) попытка {attempt+1}/3 ошибка: {e}')
            time.sleep(2)
        if translated_core:
            break

    if not translated_core:
        print(f'  Все сервисы упали, оставляем английский')
        translated_core = core

    translated_core = restore_placeholders(translated_core, token_map)

    return leading + translated_core + trailing


def escape_xml(text):
    return text.replace('&', '&').replace('<', '<').replace('>', '>')


def read_skip_list(filepath):
    skip_set = set()
    if not os.path.exists(filepath):
        return skip_set
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            skip_set.add(line)
    return skip_set


def read_translate_dict(filepath):
    translate_dict = {}
    if not os.path.exists(filepath):
        return translate_dict
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = re.match(r'^(\w+)\s*=\s*(["\'])(.+?)\2\s*;$', line)
            if not match:
                print(f'Предупреждение: translate.txt:{line_num}: неверный формат строки, пропуск: {line}')
                continue
            key = match.group(1)
            quote = match.group(2)
            value = match.group(3)
            if quote == '"' and '"' in value:
                print(f'Предупреждение: translate.txt:{line_num}: двойная кавычка внутри значения в двойных кавычках, пропуск: {line}')
                continue
            if quote == "'" and "'" in value:
                print(f'Предупреждение: translate.txt:{line_num}: одинарная кавычка внутри значения в одинарных кавычках, пропуск: {line}')
                continue
            translate_dict[key] = value
    return translate_dict


def main():
    print('Чтение en.xml...')
    en_keys = read_xml_keys('en.xml')
    print(f'Ключей в en.xml: {len(en_keys)}')

    print('Чтение ru.xml...')
    ru_keys = read_xml_keys('ru.xml')
    print(f'Ключей в ru.xml: {len(ru_keys)}')

    skip_set = read_skip_list('skip.txt')
    translate_dict = read_translate_dict('translate.txt')
    print(f'Исключено через skip.txt: {len(skip_set)}')
    print(f'Ручных переводов в translate.txt: {len(translate_dict)}')

    missing_keys = [k for k in en_keys if k not in ru_keys]
    print(f'Не хватает ключей: {len(missing_keys)}')

    skipped_keys = [k for k in missing_keys if k in skip_set]
    missing_keys = [k for k in missing_keys if k not in skip_set]
    if skipped_keys:
        print(f'Пропущено через skip.txt: {len(skipped_keys)}')

    manual_translations = {}
    for key in list(missing_keys):
        if key in translate_dict:
            manual_translations[key] = translate_dict[key]
            missing_keys.remove(key)

    for key in translate_dict:
        if key in ru_keys:
            print(f'Предупреждение: ручной перевод для "{key}" проигнорирован (уже есть в ru.xml)')
        elif key not in en_keys and key not in ru_keys:
            print(f'Предупреждение: ключ "{key}" из translate.txt не найден ни в en.xml, ни в ru.xml')

    print(f'Ключей для машинного перевода: {len(missing_keys)}')
    print(f'Ключей с ручным переводом: {len(manual_translations)}')

    if not missing_keys and not manual_translations:
        print('Недостающих ключей нет. Выход.')
        return

    with open('ru.xml', 'r', encoding='utf-8', newline='') as f:
        ru_content = f.read()

    with open('ru_patched.xml', 'w', encoding='utf-8', newline='') as f:
        f.write(ru_content)

    root_open, root_close = extract_root_tag(ru_content)
    insert_pos = ru_content.rfind(root_close)
    if insert_pos == -1:
        print('Ошибка: не найден закрывающий тег корня')
        return

    translated_count = 0
    failed_count = 0
    total = len(missing_keys)
    start_time = time.time()

    new_lines = []
    for i, key in enumerate(missing_keys, 1):
        en_value = en_keys[key]
        print(f'[{i}/{total}] Перевод: {key}')

        ru_value = translate_text(en_value)
        if ru_value == en_value.strip() and en_value.strip():
            failed_count += 1
        else:
            translated_count += 1

        escaped = escape_xml(ru_value)
        new_lines.append(f"<t name='{key}'>{escaped}</t>")

        if i % 10 == 0:
            elapsed = time.time() - start_time
            print(f'--- обработано {i}/{total}, прошло {elapsed:.1f} сек ---')

        time.sleep(0.3)

    for key, value in manual_translations.items():
        escaped = escape_xml(value)
        new_lines.append(f"<t name='{key}'>{escaped}</t>")

    insertion = '\n' + '\n'.join(new_lines) + '\n'
    patched_content = ru_content[:insert_pos] + insertion + ru_content[insert_pos:]

    with open('ru_patched.xml', 'w', encoding='utf-8', newline='') as f:
        f.write(patched_content)

    elapsed = time.time() - start_time
    print(f'\nГотово!')
    print(f'Переведено машинно: {translated_count}')
    print(f'Взято из translate.txt: {len(manual_translations)}')
    print(f'Пропущено через skip.txt: {len(skipped_keys)}')
    print(f'Осталось английскими (ошибки сервиса): {failed_count}')
    print(f'Время: {elapsed:.1f} сек')
    print(f'Результат записан в {os.path.abspath("ru_patched.xml")}')


if __name__ == '__main__':
    main()