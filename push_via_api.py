# -*- coding: utf-8 -*-
"""github.com 主站被阻断时的替代推送方案:通过 api.github.com 的 Contents API
上传仓库文件(与 git push 等价,内容一致)。由用户本人运行。
"""
import base64, json, subprocess, os, urllib.parse, sys

REPO = "cometww/jingzhi-cockpit"
FILES = [
    "index.html",
    "公司经营驾驶舱_20260920_1633.html",
    "经营分析更新服务_20260920_1625.py",
    "启动经营分析更新服务_20260920_1625.bat",
]

def gh(*args):
    r = subprocess.run(["gh", "api", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r

ok = True
for f in FILES:
    if not os.path.exists(f):
        print("[SKIP] 跳过:", f)
        continue
    path = urllib.parse.quote(f, safe="")
    # 1. 取当前 sha(更新已有文件需要)
    r = gh("repos/%s/contents/%s" % (REPO, path))
    sha = None
    try:
        sha = json.loads(r.stdout).get("sha")
    except Exception:
        pass
    # 2. 构造请求体
    body = {
        "message": "update v2: 周报全文明细+任务催办页+手机端兜底",
        "content": base64.b64encode(open(f, "rb").read()).decode(),
    }
    if sha:
        body["sha"] = sha
    json.dump(body, open("_body.json", "w", encoding="utf-8"), ensure_ascii=False)
    # 3. PUT 上传
    r = gh("-X", "PUT", "repos/%s/contents/%s" % (REPO, path), "--input", "_body.json")
    if r.returncode == 0 and '"sha"' in (r.stdout or ""):
        print("[OK] 已上传:", f)
    else:
        ok = False
        print("[FAIL] 失败:", f, (r.stdout or r.stderr)[:300])

os.remove("_body.json") if os.path.exists("_body.json") else None
print("[DONE] 全部完成" if ok else "[WARN] 存在失败项,请检查输出")
