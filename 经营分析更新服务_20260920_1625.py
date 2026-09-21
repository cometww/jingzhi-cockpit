# -*- coding: utf-8 -*-
"""公司经营分析 · 本地更新检测服务 v2(仅监听 127.0.0.1:8765)

GET  /api/check     → 递归扫描 D:\上海精智\2026\AI管理\公司月度经营 全部 PDF,
                     与《已分析清单》(公司经营分析_清单.json)比对,
                     返回 新增/修改/删除 明细(文件名称/修改时间/大小)。
                     首次运行自动建立基线。清单=已分析过的文件记录。
POST /api/analyze   → 若有变化:生成《公司经营分析_待更新_YYYYMMDD_HHMM.md》任务文件,
                     记录变化清单与增量分析指引;页面提示用户把任务交给 Claude 执行。
                     无变化则返回"无需分析"。
GET  /api/status    → 返回最近一次任务状态。
无第三方依赖,Python 标准库即可运行。
"""
import json, os, subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime

FOLDER   = r"D:\上海精智\2026\AI管理\公司月度经营"
MDDIR    = r"D:\个人资料\Claude\MD"
MANIFEST = os.path.join(MDDIR, "公司经营分析_清单.json")
STATUS   = os.path.join(MDDIR, "公司经营分析_状态.json")
PORT     = 8765
WEEKLY_GROUP = "cidbNtRNiwctEb+7w73IOleNg=="   # 钉钉「执委会」群(管理层周报)

def scan():
    items = {}
    if os.path.isdir(FOLDER):
        for dirpath, _, files in os.walk(FOLDER):
            for f in files:
                if not f.lower().endswith(".pdf"):
                    continue
                p = os.path.join(dirpath, f)
                rel = os.path.relpath(p, FOLDER).replace("\\", "/")
                st = os.stat(p)
                items[rel] = {"size": st.st_size, "mtime": int(st.st_mtime)}
    return items

def mtime_str(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""

def load_json(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None

def save_json(path, obj):
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def weekly_state():
    """用 dws 抓执委会群近14天周报,返回 {姓名: 最新createTime};失败返回 None。"""
    from datetime import timedelta
    try:
        p = subprocess.run(
            ["dws", "chat", "+chat-messages", "--group", WEEKLY_GROUP,
             "--start", (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d"), "--page-all",
             "--max-items", "300", "-f", "json", "-y"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
        data = json.loads(p.stdout)
        latest = {}
        for m in data.get("messages") or []:
            t = m.get("text") or ""
            if "周报" not in t:
                continue
            s = m.get("sender", "?")
            ct = m.get("createTime", "")
            if s not in latest or ct > latest[s]:
                latest[s] = ct
        return latest
    except Exception:
        return None

def diff_check(save=False):
    """比对清单(文件夹 + 管理层周报)。save=True 时把当前状态写回清单。"""
    now = scan()
    mf = load_json(MANIFEST)
    if mf is None or "files" not in mf:
        wk = weekly_state() or {}
        save_json(MANIFEST, {"files": now, "weekly": wk,
                             "updatedAt": datetime.now().isoformat(), "lastUpdates": []})
        return False, [], []
    base = mf["files"]
    ups = []
    for f, v in now.items():
        if f not in base:
            ups.append({"type": "新增", "file": f, "mtime": mtime_str(v["mtime"]), "size": v["size"]})
        elif v != base[f]:
            ups.append({"type": "修改", "file": f, "mtime": mtime_str(v["mtime"]), "size": v["size"]})
    for f in base:
        if f not in now:
            ups.append({"type": "删除", "file": f, "mtime": "", "size": 0})
    # 管理层周报比对(每人最新一期时间)
    wk_ok = False
    wk = weekly_state()
    if wk is not None:
        wk_ok = True
        base_wk = mf.get("weekly", {})
        for person, ct in wk.items():
            if person not in base_wk:
                ups.append({"type": "周报更新", "file": f"{person} 的新周报({ct[:16]})",
                            "mtime": ct[:16], "size": 0})
            elif ct > base_wk[person]:
                ups.append({"type": "周报更新", "file": f"{person} 的新周报({ct[:16]})",
                            "mtime": ct[:16], "size": 0})
    if ups and save:
        mf["files"] = now
        if wk_ok:
            mf["weekly"] = wk
        mf["updatedAt"] = datetime.now().isoformat()
        mf["lastUpdates"] = ups
        save_json(MANIFEST, mf)
    return len(ups) > 0, ups, mf.get("lastUpdates", [])

def write_task(ups):
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    task_path = os.path.join(MDDIR, f"公司经营分析_待更新_{ts}.md")
    lines = [f"- {u['type']}: {u['file']}(修改时间 {u['mtime']},大小 {u['size']/1024/1024:.1f}MB)" for u in ups]
    content = f"""# 公司经营分析 · 待更新任务

> 生成时间:{datetime.now().strftime("%Y-%m-%d %H:%M")}
> 状态:待 Claude 执行增量分析

## 资料变化清单(与已分析清单比对)

{chr(10).join(lines)}

## 增量分析指引(三部分都要更新)

**① 文件夹资料(月度经营报告/营销汇报/其他关键主题)**
1. 用 pypdf 提取变化 PDF 文本,识别月份归属(月度经营报告/营销管理中心汇报/其他主题报告);
2. 按报告既有结构增量更新 `D:\\个人资料\\Claude\\MD\\公司经营驾驶舱_20260920_1633.html`:
   - 新月份经营报告 → MONTHS 数组新增月份对象(自动成为新页签);
   - 新的营销汇报 → 更新对应月份 mkt 字段;
   - 新的主题报告 → 更新 TOPICS 数组("其他关键主题"页签);
   - 同步更新"公司汇总"页签(月度趋势、业绩曲线、现金流曲线、营销总览)与图表数据;

**② 管理层最新周报(钉钉执委会群)**
3. 抓取执委会群最新周报:
   `dws chat +chat-messages --group "cidbNtRNiwctEb+7w73IOleNg==" --start "<近10天>" --page-all --max-items 400 -f json -y`
   - 筛选含"周报"的消息;**每人只保留最新一期**(按 createTime 去重,剔除更早历史期次);
   - 更新 WEEKLY 数组:姓名/职位/来源时间(createTime)/期次(W37/W38...)/摘要条目(提取文字内容,表格图片标注"详见附件")/原文链接(landray URL);
   - 同步更新 WEEKLY.key 关键数据与 WEEKLY.updatedAt;

**③ 通用规范**
4. 金额单位万元;未披露标注"未披露"不臆造;区分数据事实/分析判断;建议带优先级与责任层级;
5. 完成后 node --check 校验 JS,Edge headless 验证渲染;
6. 只做增量,不改动历史内容。
"""
    open(task_path, "w", encoding="utf-8").write(content)
    save_json(STATUS, {"state": "task_ready",
                       "taskFile": os.path.basename(task_path),
                       "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       "updates": ups})
    return task_path

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith("/api/check"):
            has, ups, last = diff_check()
            self._json({"hasUpdate": has, "updates": ups, "lastUpdates": last,
                        "checkedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "message": ("发现更新,需要重新分析" if has else "无更新,无需重新分析")})
        elif self.path.startswith("/api/status"):
            st = load_json(STATUS) or {"state": "idle", "result": ""}
            self._json(st)
        else:
            self._json({"ok": True, "service": "经营分析更新检测服务 v2",
                        "hint": "GET /api/check | POST /api/analyze | GET /api/status"})
    def do_OPTIONS(self):
        """响应浏览器 CORS 预检请求(否则带 JSON 头的 POST 会被浏览器拦截)"""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()
    def do_POST(self):
        if self.path.startswith("/api/analyze"):
            has, ups, _ = diff_check(save=True)
            if not has:
                self._json({"hasUpdate": False, "message": "无更新,无需重新分析",
                            "checkedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            else:
                task = write_task(ups)
                self._json({"hasUpdate": True,
                            "message": "已生成待更新任务文件",
                            "taskFile": task,
                            "updates": ups})
        elif self.path.startswith("/api/urge"):
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            except Exception:
                body = {}
            person = (body.get("person") or "").strip()
            uid = (body.get("uid") or "").strip()
            msg = (body.get("msg") or "").strip()
            if not person or not msg:
                self._json({"ok": False, "message": "缺少 person/msg 参数"})
                return
            if body.get("dry"):
                self._json({"ok": True, "dry": True, "person": person, "msg": msg})
                return
            # 优先按 userId 直发(解决重名歧义,如"刘超");否则按姓名解析发送
            cmd = (["dws", "chat", "+messages-send", "--as", "user", "--user", uid, "--text", msg, "-y"]
                   if uid else
                   ["dws", "chat", "+dm", "--to", person, "--content", msg, "-y"])
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=120)
                detail = (p.stdout or p.stderr or "")[:400]
                ok_flag = p.returncode == 0 and ("success" in detail.lower() or "errorcode" in detail.lower() and "null" in detail.lower())
                self._json({"ok": ok_flag, "person": person,
                            "sentAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "detail": detail})
            except Exception as e:
                self._json({"ok": False, "message": "发送失败: %s" % e})
        else:
            self._json({"ok": False, "message": "unknown endpoint"})

if __name__ == "__main__":
    print("经营分析更新检测服务 v2 已启动: http://127.0.0.1:8765")
    print("监控目录:", FOLDER)
    print("GET /api/check | POST /api/analyze | GET /api/status")
    print("保持本窗口打开,关闭即停止服务。")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
