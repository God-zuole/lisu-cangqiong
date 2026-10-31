import io
import os
import re
import sys


def dedup(path):
    L = io.open(path, encoding='utf-8').read().split('\n')

    # 1. 丢掉一切明显不是正文的行（工具调用残渣）
    drop = re.compile(r'^(<｜|写文件|改。$|字数估算|这个结尾|重写结尾|不，钩子|注意：|档案：|所以改成|另外"|还有：)')
    L = [l for l in L if not drop.match(l.strip())]

    # 2. 找标题行位置；出现两次说明正文整段重复
    head = [i for i, l in enumerate(L) if l.startswith('# 第')]
    if len(head) >= 2:
        L = L[:head[1]]
    # 3. 兜底：找第一句重复出现的位置
    else:
        first = next((l for l in L if l.strip() and not l.startswith('#')), None)
        if first:
            idx = [i for i, l in enumerate(L) if l.strip() == first.strip()]
            if len(idx) >= 2:
                L = L[:idx[1]]

    # 4. 去掉尾部空行
    while L and not L[-1].strip():
        L.pop()

    io.open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
    n = len(re.sub(r'\s', '', '\n'.join(L[1:])))
    return n


if __name__ == '__main__':
    for p in sys.argv[1:]:
        print('%s -> %d 字' % (os.path.basename(p), dedup(p)))
