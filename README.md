# 儿童汉字听写 App

**版本**：v3.0
**日期**：2026-05-17
**孩子端用户名**：小树（勋章页机器人名：Trey）

---

## 一、产品定位

| 维度 | 内容 |
|------|------|
| 目标用户 | 小学生子女（孩子端）+ 家长（家长端） |
| 核心场景 | 孩子独立完成听写/看拼音写 → 家长异步批改 → 错字自动记入错题本 → 持续复习直至掌握 |
| 核心价值 | 异步听写流程（解放家长）+ 游戏化激励（积分/等级/勋章） |
| 产品形态 | 双前端（孩子端 App / 家长端 App）+ 单后端 API + TTS 服务 |
| TTS 声音 | 微软 Azure 晓晓（女声，活泼） |

---

## 二、整体架构

```
┌────────────────────────────────────────────────────────────────┐
│                        服务器（当前主机）                        │
│                                                                 │
│  ┌──────────────────┐                                           │
│  │  孩子端前端 student/  │◄─── REST ───┐                        │
│  │  http-server         │              │                        │
│  │  端口 3000           │              ▼                        │
│  └──────────────────┘        ┌──────────────────────────────┐ │
│                                │       后端 API（Flask）        │ │
│  ┌──────────────────┐        │       端口 8080              │ │
│  │  家长端前端 parent/    │◄─── REST ───┤                        │ │
│  │  http-server         │              │                        │ │
│  │  端口 3001           │              ▼                        │ │
│  └──────────────────┘        ┌──────────────────────────────┐ │
│                                │       SQLite                  │ │
│  ┌──────────────────┐        │   dictation.db                │ │
│  │  TTS 服务 edge-tts │        │       持久化存储              │ │
│  │  端口 8082         │◄───────┴──────────────────────────────┘ │
│  └──────────────────┘                    │                      │
│                                           │  新待批改时            │
│                                    ┌──────▼──────┐              │
│                                    │  Hermes     │               │
│                                    │  发飞书消息 │               │
│                                    │  通知 Stan  │               │
│                                    └─────────────┘               │
└────────────────────────────────────────────────────────────────┘

部署方式：systemd service，全部开机自启，failed 自动重启
```

---

## 三、目录结构

```
dictation_app_package/
├── README.md                          # 本文件
├── dictation.db                       # SQLite 数据库（运行时创建）
│
├── backend/                           # 后端服务
│   ├── app.py                         # Flask API 主程序（端口 8080）
│   ├── tts.py                         # TTS 服务 edge-tts（端口 8082）
│   ├── init_db.py                     # 数据库初始化脚本（含字库导入）
│   ├── import_semester2.py            # 补充导入字库脚本
│   ├── migrate_semester2.py           # 数据迁移脚本
│   ├── sessions/                      # 练习 session 临时数据（JSON）
│   └── uploads/                       # 书写图片存储（文件）
│
├── student/                           # 孩子端前端
│   ├── index.html                     # 首页 Dashboard（显示进度/等级/勋章入口）
│   ├── dictation.html                 # 听写/看拼音写 练习页
│   ├── review.html                    # 错题复习页
│   ├── profile.html                  # 积分/等级/勋章页
│   └── style.css                     # 共享样式
│
├── parent/                            # 家长端前端
│   ├── index.html                    # 首页（含待批改数量徽章）
│   ├── pending.html                  # 待批改列表
│   ├── grade.html                    # 批改页
│   ├── wrongbook.html               # 错题本查看页
│   └── style.css                    # 共享样式
│
├── grading_server.py                  # 家长批改页面服务器（端口 8081）
└── reverse_proxy.py                   # 听写提交反向代理（端口 3000）
```

---

## 四、服务说明

| 服务 | 端口 | 技术栈 | 说明 |
|------|------|--------|------|
| `app.py` | 8080 | Flask + SQLite | 听写后端 API：题目获取、提交、批改、积分/等级/勋章 |
| `tts.py` | 8082 | edge-tts | TTS 文字转语音，调用微软 Azure 晓晓 |
| `grading_server.py` | 8081 | 内置 HTTP | 家长批改页面，显示书写图片并逐字标记对错 |
| `reverse_proxy.py` | 3000 | 内置 HTTP | 听写提交反向代理，将请求转发至 app.py |
| 学生端静态服务 | 3000 | http-server | 孩子端前端静态文件 |
| 家长端静态服务 | 3001 | http-server | 家长端前端静态文件 |

> **注意**：`reverse_proxy.py`（端口 3000）和学生端 `http-server`（端口 3000）**不能同时运行**，共用同一端口。

---

## 五、勋章体系

| badge_key | 名称 | 图标 | 解锁条件 |
|-----------|------|------|----------|
| `first_practice` | 初次练习 | 🌱 | 完成第 1 次练习 |
| `streak_3` | 连续 3 天 | 🔥 | 连续练习 3 天 |
| `perfect_10` | 十全十美 | 💯 | 单次练习 10 字全对 |
| `neat_writer` | 整洁书写 | ✍️ | 单次练习连续 5 字全对 |
| `wrongbook_cleared_20` | 错字清道夫 | 🧹 | 累计复习 20 个错字 |
| `streak_7` | 连续 7 天 | 📆 | 连续练习 7 天 |
| `hundred_perfect` | 百分达人 | 🏆 | 累计 100 字全对 |
| `monthly_practitioner` | 月度练习家 | 📅 | 累计练习 30 天 |
| `lv10` | 全能小王 | 👑 | 达到 Lv10 |

---

## 六、等级体系

| 等级 | 名称 | 所需 session 数 |
|------|------|----------------|
| 1 | 书写启蒙 | 1 |
| 2 | 书写新手 | 2 |
| 3 | 书写进阶 | 3 |
| 4 | 书写能手 | 5 |
| 5 | 书写达人 | 8 |
| 6 | 书写高手 | 12 |
| 7 | 书写专家 | 17 |
| 8 | 书写大师 | 23 |
| 9 | 书写宗师 | 30 |
| 10 | 全能小王 | 40 |

---

## 七、数据库表结构

| 表名 | 说明 |
|------|------|
| `child` | 孩子信息：姓名、积分、等级、连胜天数、上次练习日期 |
| `words` | 字库：汉字、拼音、单元 ID、单元名称 |
| `sessions` | 练习记录：模式、状态（draft/submitted/graded）、正确字数 |
| `session_chars` | 练习详情：每个字符的图片路径与对错结果 |
| `wrongbook` | 错题本：错字、错误次数、正确次数、是否已复习 |
| `badges` | 勋章定义（种子数据，启动时自动导入） |
| `child_badges` | 孩子已解锁的勋章 |
| `reward_logs` | 奖励兑换记录 |

---

## 八、快速部署

### 8.1 环境要求

- Python 3.10+
- Node.js（用于 http-server 静态服务）
- edge-tts：`pip install edge-tts`
- flask + flask-cors：`pip install flask flask-cors`

### 8.2 初始化数据库

```bash
cd /path/to/dictation_app_package
python3 backend/init_db.py
```

### 8.3 启动所有服务

```bash
# 后端 API（端口 8080）
python3 backend/app.py &

# TTS 服务（端口 8082）
python3 backend/tts.py &

# 批改服务器（端口 8081）
python3 grading_server.py &

# 孩子端前端（端口 3000）
cd student && npx http-server -p 3000 -c-1 &

# 家长端前端（端口 3001）
cd parent && npx http-server -p 3001 -c-1 &
```

或使用 systemd service（见 `deploy/` 目录）。

### 8.4 访问地址

| 端 | 地址 |
|----|------|
| 孩子端 | `http://<服务器IP>:3000` |
| 家长端 | `http://<服务器IP>:3001` |
| 批改页 | `http://<服务器IP>:8081` |
| TTS 测试 | `http://<服务器IP>:8082/tts?text=金灿灿` |

---

## 九、使用流程

### 孩子端

1. 打开首页，选择年级和单元
2. 进入听写页，系统朗读汉字，孩子在米字格中书写
3. 每写完一个字，点「下一个 →」保存图片并进入下一个
4. 全部完成后提交，系统推送飞书通知给家长
5. 可在「我的勋章」页查看已解锁勋章

### 家长端

1. 打开 `http://<IP>:3001`，查看待批改数量
2. 进入批改页，逐字标记对（✓）或错（✗）
3. 提交后系统自动更新错题本，并给孩子积分/勋章反馈

---

## 十、部署脚本

项目包中包含 `deploy/` 目录，提供 systemd service 文件和启动脚本。

```bash
deploy/
├── start.sh              # 一键启动所有服务
├── stop.sh               # 停止所有服务
└── dictation-app.service # systemd service 文件（Ubuntu/Debian）
```

---

## 十一、数据库维护

### 手动添加字词

```bash
cd /root/dictation_app
sqlite3 dictation.db
```

```sql
-- 查看字库
SELECT unit_name, COUNT(*) FROM words GROUP BY unit_id;

-- 查看当前勋章
SELECT b.name, b.icon, cb.earned_at
FROM child_badges cb
JOIN badges b ON cb.badge_id = b.id
WHERE cb.child_id = 1;
```

### 重置数据（清空孩子进度，保留字库和勋章定义）

```sql
DELETE FROM session_chars;
DELETE FROM sessions;
DELETE FROM child_badges;
DELETE FROM wrongbook;
DELETE FROM reward_logs;
UPDATE child SET points=0, level=1, streak_days=0, last_practice=NULL WHERE id=1;
```

---

## 十二、常见问题

**503 Service Unavailable（TTS）**
→ 检查 edge-tts 是否可用：`edge-tts --list-voices`

**批改后孩子没收到勋章通知**
→ 检查飞书机器人配置，确保 lark-cli 已绑定正确账号

**页面打不开**
→ 确认 http-server 已启动并绑定 `0.0.0.0` 而非 `127.0.0.1`

---

## 十三、授权

本项目为智联招聘内部工具，未经授权禁止外传。
