"""
init_db.py — 初始化 SQLite 数据库并导入字库
二年级下册语文教材 · 约 300+ 字词
"""

import sqlite3, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "..", "dictation.db")

# ── 字库原始数据 ─────────────────────────────────────────────
WORD_DATA = [
    ("识字1",  "识字1",  "神,中华,山川,长江,长城,民族,情,各,齐"),
    ("识字2",  "识字2",  "传统,节日,春节,花灯,清明,先人,龙舟,端午,中秋,团圆,体贴,街道,艾草,真实"),
    ("识字3",  "识字3",  "故事,生活,甲骨文,样子,币,钱财,有关,感觉,品质,与众不同"),
    ("识字4",  "识字4",  "美食,茄子,烤鸭,水鱼,羊肉,蛋炒饭,母鸡"),
    ("阅读1",  "阅读1",  "碧绿,化妆,丝,剪刀,童话,回归"),
    ("阅读2",  "阅读2",  "春天,寻,茅毛,野花,柳枝,桃花,冲洗,新闻,回荡"),
    ("阅读3",  "阅读3",  "鲜花,先生,原来,大叔,太太,客,奇,快活,美好,礼物,通过"),
    ("阅读4",  "阅读4",  "碧空如洗,万里无云,格外,注目,休息,小心,笔直,满意"),
    ("园地一", "园地一", "剧烈,操场"),
    ("阅读5",  "阅读5",  "雷锋,叔叔,昨天,温,爱,背包,脱,汗水"),
    ("阅读6",  "阅读6",  "好奇,也许,子,平时,难道,平常,农民,加工,农具,甜菜,工具,劳动,应该,尝,买卖,甘甜,果汁"),
    ("阅读7",  "阅读7",  "弱小,周末,父母,吸,芬芳,雨衣,为什么,勇敢,快递"),
    ("园地二", "园地二", "美术,衣服,任务"),
    ("阅读8",  "阅读8",  "彩色,铅笔盒,森林,雪松,歌声,精灵,季节,流动,结束"),
    ("阅读9",  "阅读9",  "出色,妹妹,碧,波纹,恋不舍,柳树,柳条,不时,马匹,不舍,追求,奔跑"),
    ("阅读10", "阅读10", "绿色,一直,说话,童话,阿姨,发现,弟弟,发明,字母,上升,旁边"),
    ("园地四", "园地四", "克服"),
    ("阅读11", "阅读11", "亡羊补牢,告,禾苗,力气,明白,丢失,帮助,坏事,死亡"),
    ("阅读12", "阅读12", "杨桃,图画,讲桌,座位,室,老老实实,时候,哈哈大笑,五角星,画,神情,安排,举手"),
    ("阅读13", "阅读13", "愿意,飞快,为难,伯伯,立刻,突然,吃,认真,难为情,麦田"),
    ("园地五", "园地五", "空洞,洞穴"),
    ("阅读14", "阅读14", "包含,南,东吴,洁净,白莲"),
    ("阅读15", "阅读15", "雷雨,乌云,黑沉,闪电,雷声,窗户,清新,压力,响亮"),
    ("阅读16", "阅读16", "野外,天然,指南,方向,忠实,指点,北极星,永远,黑夜,帮忙,特别,积雪"),
    ("阅读17", "阅读17", "航天员,宇宙飞船,空间站,活动,主要,方便,直接,浴桶,清理,实在"),
    ("园地六", "园地六", "图书馆,场所"),
    ("阅读18", "阅读18", "大象,耳朵,扇子,慢慢,遇到,一定,每天,经常,人家,根本"),
    ("阅读19", "阅读19", "店,河马,工夫,终于,星期,需要"),
    ("阅读20", "阅读20", "青蛙,野鸭,泉水,花丛,尽情,游泳,出卖,搬运,砍树,破旧"),
    ("阅读21", "阅读21", "新奇,目光,仿佛,周游,任何,纺织,怎样,灵巧,花纹,迟到"),
    ("园地七", "园地七", "校园"),
    ("阅读22", "阅读22", "开始,光明,值日,决心,从此,欢唱,生机,弓箭"),
    ("阅读23", "阅读23", "传说,首,步行,忽然,启发,民众,自由,道理,果然,便利,条件,完全,忘却"),
    ("阅读24", "阅读24", "洪水,痛苦,百姓,必须,治服,继续,奔波,带领,农业,安居乐业"),
    ("园地八", "园地八", "金灿灿"),
]

# ── 勋章定义 ─────────────────────────────────────────────────
BADGES = [
    ("first_practice",       "初出茅庐",    "🌱", "完成第1次练习",                         0),
    ("neat_writer",          "认真书写",    "📝", "连续5字全对（单次练习）",               0),
    ("streak_3",             "连续作战",    "🔥", "连续3天练习",                           0),
    ("perfect_10",           "一字不差",    "⭐", "单次10字全对",                          0),
    ("wrongbook_cleared_20", "错题终结者",  "📕", "累计复习20个错字",                     0),
    ("streak_7",             "一周坚持",    "🏆", "连续7天练习",                           0),
    ("hundred_perfect",      "百发百中",    "🎯", "累计100字全对",                         0),
    ("monthly_practitioner", "满勤小达人",  "👑", "累计练习30天",                         0),
    ("lv10",                 "全能小王",    "🐉", "达到Lv10",                             0),
]

# ── 拼音映射（常用字） ────────────────────────────────────────
PINYIN_MAP = {
    "神":"shén","中华":"zhōng huá","山川":"shān chuān","长江":"cháng jiāng","长城":"cháng chéng",
    "民族":"mín zú","情":"qíng","各":"gè","齐":"qí",
    "传统":"chuán tǒng","节日":"jié rì","春节":"chūn jié","花灯":"huā dēng","清明":"qīng míng",
    "先人":"xiān rén","龙舟":"lóng zhōu","端午":"duān wǔ","中秋":"zhōng qiū","团圆":"tuán yuán",
    "体贴":"tǐ tiē","街道":"jiē dào","艾草":"ài cǎo","真实":"zhēn shí",
    "故事":"gù shi","生活":"shēng huó","甲骨文":"jiǎ gǔ wén","样子":"yàng zi","币":"bì",
    "钱财":"qián cái","有关":"yǒu guān","感觉":"gǎn jué","品质":"pǐn zhì","与众不同":"yǔ zhòng bù tóng",
    "美食":"měi shí","茄子":"qié zi","烤鸭":"kǎo yā","水鱼":"shuǐ yú","羊肉":"yáng ròu",
    "蛋炒饭":"dàn chǎo fàn","母鸡":"mǔ jī",
    "碧绿":"bì lǜ","化妆":"huà zhuāng","丝":"sī","剪刀":"jiǎn dao","童话":"tóng huà","回归":"huí guī",
    "春天":"chūn tiān","寻":"xún","茅毛":"máo máo","野花":"yě huā","柳枝":"liǔ zhī","桃花":"táo huā",
    "冲洗":"chōng xǐ","新闻":"xīn wén","回荡":"huí dàng",
    "鲜花":"xiān huā","先生":"xiān sheng","原来":"yuán lái","大叔":"dà shū","太太":"tài tai",
    "客":"kè","奇":"qí","快活":"kuài huo","美好":"měi hǎo","礼物":"lǐ wù","通过":"tōng guò",
    "碧空如洗":"bì kōng rú xǐ","万里无云":"wàn lǐ wú yún","格外":"gé wài","注目":"zhù mù",
    "休息":"xiū xi","小心":"xiǎo xīn","笔直":"bǐ zhí","满意":"mǎn yì",
    "剧烈":"jù liè","操场":"cāo chǎng",
    "雷锋":"léi fēng","叔叔":"shū shu","昨天":"zuó tiān","温":"wēn","爱":"ài","背包":"bèi bāo","脱":"tuō","汗水":"hàn shuǐ",
    "好奇":"hào qí","也许":"yě xǔ","子":"zi","平时":"píng shí","难道":"nán dào","平常":"píng cháng",
    "农民":"nóng mín","加工":"jiā gōng","农具":"nóng jù","甜菜":"tián cài","工具":"gōng jù",
    "劳动":"láo dòng","应该":"yīng gāi","尝":"cháng","买卖":"mǎi mài","甘甜":"gān tián","果汁":"guǒ zhī",
    "弱小":"ruò xiǎo","周末":"zhōu mò","父母":"fù mǔ","吸":"xī","芬芳":"fēn fāng","雨衣":"yǔ yī",
    "为什么":"wèi shén me","勇敢":"yǒng gǎn","快递":"kuài dì",
    "美术":"měi shù","衣服":"yī fu","任务":"rèn wu",
    "彩色":"cǎi sè","铅笔盒":"qiān bǐ hé","森林":"sēn lín","雪松":"xuě sōng","歌声":"gē shēng",
    "精灵":"jīng líng","季节":"jì jié","流动":"liú dòng","结束":"jié shù",
    "出色":"chū sè","妹妹":"mèi mei","碧":"bì","波纹":"bō wén","恋不舍":"liàn bù shě","柳树":"liǔ shù",
    "柳条":"liǔ tiáo","不时":"bù shí","马匹":"mǎ pǐ","不舍":"bù shě","追求":"zhuī qiú","奔跑":"bēn pǎo",
    "绿色":"lǜ sè","一直":"yī zhí","说话":"shuō huà","童话":"tóng huà","阿姨":"ā yí","发现":"fā xiàn",
    "弟弟":"dì di","发明":"fā míng","字母":"zì mǔ","上升":"shàng shēng","旁边":"páng biān",
    "克服":"kè fú",
    "亡羊补牢":"wáng yáng bǔ láo","告":"gào","禾苗":"hé miáo","力气":"lì qi","明白":"míng bai",
    "丢失":"diū shī","帮助":"bāng zhù","坏事":"huài shì","死亡":"sǐ wáng",
    "杨桃":"yáng táo","图画":"tú huà","讲桌":"jiǎng zhuō","座位":"zuò wèi","室":"shì",
    "老老实实":"lǎo lao shí shí","时候":"shí hou","哈哈大笑":"hā hā dà xiào","五角星":"wǔ jiǎo xīng",
    "画":"huà","神情":"shén qíng","安排":"ān pái","举手":"jǔ shǒu",
    "愿意":"yuàn yì","飞快":"fēi kuài","为难":"wéi nán","伯伯":"bó bo","立刻":"lì kè","突然":"tū rán",
    "吃":"chī","认真":"rèn zhēn","难为情":"nán wéi qíng","麦田":"mài tián",
    "空洞":"kōng dòng","洞穴":"dòng xué",
    "包含":"bāo hán","南":"nán","东吴":"dōng wú","洁净":"jié jìng","白莲":"bái lián",
    "雷雨":"léi yǔ","乌云":"wū yún","黑沉":"hēi chén","闪电":"shǎn diàn","雷声":"léi shēng",
    "窗户":"chuāng hu","清新":"qīng xīn","压力":"yā lì","响亮":"xiǎng liàng",
    "野外":"yě wài","天然":"tiān rán","指南":"zhǐ nán","方向":"fāng xiàng","忠实":"zhōng shí",
    "指点":"zhǐ diǎn","北极星":"běi jí xīng","永远":"yǒng yuǎn","黑夜":"hēi yè","帮忙":"bāng máng",
    "特别":"tè bié","积雪":"jī xuě",
    "航天员":"háng tiān yuán","宇宙飞船":"yǔ zhòu fēi chuán","空间站":"kōng jiān zhàn","活动":"huó dòng",
    "主要":"zhǔ yào","方便":"fāng biàn","直接":"zhí jiē","浴桶":"yù tǒng","清理":"qīng lǐ","实在":"shí zài",
    "图书馆":"tú shū guǎn","场所":"chǎng suǒ",
    "大象":"dà xiàng","耳朵":"ěr duo","扇子":"shàn zi","慢慢":"màn màn","遇到":"yù dào",
    "一定":"yī dìng","每天":"měi tiān","经常":"jīng cháng","人家":"rén jia","根本":"gēn běn",
    "店":"diàn","河马":"hé mǎ","工夫":"gōng fu","终于":"zhōng yú","星期":"xīng qī","需要":"xū yào",
    "青蛙":"qīng wā","野鸭":"yě yā","泉水":"quán shuǐ","花丛":"huā cóng","尽情":"jìn qíng",
    "游泳":"yóu yǒng","出卖":"chū mài","搬运":"bān yùn","砍树":"kǎn shù","破旧":"pò jiù",
    "新奇":"xīn qí","目光":"mù guāng","仿佛":"fǎng fú","周游":"zhōu yóu","任何":"rèn hé",
    "纺织":"fǎng zhī","怎样":"zěn yàng","灵巧":"líng qiǎo","花纹":"huā wén","迟到":"chí dào",
    "校园":"xiào yuán",
    "开始":"kāi shǐ","光明":"guāng míng","值日":"zhí rì","决心":"jué xīn","从此":"cóng cǐ",
    "欢唱":"huān chàng","生机":"shēng jī","弓箭":"gōng jiàn",
    "传说":"chuán shuō","首":"shǒu","步行":"bù xíng","忽然":"hū rán","启发":"qǐ fā",
    "民众":"mín zhòng","自由":"zì yóu","道理":"dào lǐ","果然":"guǒ rán","便利":"biàn lì",
    "条件":"tiáo jiàn","完全":"wán quán","忘却":"wàng què",
    "洪水":"hóng shuǐ","痛苦":"tòng kǔ","百姓":"bǎi xìng","必须":"bì xū","治服":"zhì fú",
    "继续":"jì xù","奔波":"bēn bō","带领":"dài lǐng","农业":"nóng yè","安居乐业":"ān jū lè yè",
    "金灿灿":"jīn càn càn",
}


def get_pinyin(word):
    return PINYIN_MAP.get(word, "")


def init():
    if os.path.exists(DB_PATH):
        print(f"[init_db] {DB_PATH} 已存在，跳过初始化")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ── 建表 ───────────────────────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS child (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL DEFAULT '小树',
        points INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        streak_days INTEGER DEFAULT 0,
        last_practice DATE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        char TEXT NOT NULL,
        pinyin TEXT,
        word TEXT,
        unit_id TEXT NOT NULL,
        unit_name TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER DEFAULT 1,
        session_key TEXT UNIQUE NOT NULL,
        mode TEXT NOT NULL,
        unit_ids TEXT,
        status TEXT DEFAULT 'draft',
        total_chars INTEGER DEFAULT 0,
        correct_chars INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        graded_at DATETIME
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS session_chars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
        char TEXT NOT NULL,
        word TEXT,
        pinyin TEXT,
        image_url TEXT,
        correct INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS wrongbook (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER DEFAULT 1,
        char TEXT NOT NULL,
        word TEXT,
        pinyin TEXT,
        wrong_count INTEGER DEFAULT 0,
        correct_count INTEGER DEFAULT 0,
        reviewed INTEGER DEFAULT 0,
        first_seen DATETIME,
        last_review DATETIME,
        UNIQUE(child_id, char)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS badges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        badge_key TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        icon TEXT,
        condition TEXT NOT NULL,
        points INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS child_badges (
        child_id INTEGER DEFAULT 1,
        badge_id INTEGER REFERENCES badges(id),
        earned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (child_id, badge_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reward_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER DEFAULT 1,
        reward TEXT,
        points INTEGER,
        status TEXT DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ── 周计划表 ────────────────────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS weekly_plan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER DEFAULT 1,
        week_start TEXT,
        week_end TEXT,
        status TEXT DEFAULT 'draft',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS weekly_plan_item (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        weekly_plan_id INTEGER REFERENCES weekly_plan(id),
        task_type TEXT,
        unit_id TEXT,
        unit_name TEXT,
        content TEXT,
        total_chars INTEGER DEFAULT 0,
        chars TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_task (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER DEFAULT 1,
        weekly_plan_id INTEGER REFERENCES weekly_plan(id),
        date TEXT,
        task_type TEXT,
        unit_id TEXT,
        unit_name TEXT,
        words TEXT,
        content TEXT,
        status TEXT DEFAULT 'pending',
        completed_at DATETIME
    )
    """)

    # ── 英语表 ─────────────────────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS english_words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT NOT NULL,
        word_type TEXT NOT NULL,
        pos TEXT,
        meaning TEXT,
        pronunciation TEXT,
        example TEXT,
        lesson TEXT,
        week_date TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS english_articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT,
        image_urls TEXT,
        week_date TEXT NOT NULL,
        order_num INTEGER DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS english_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER DEFAULT 1,
        date TEXT NOT NULL,
        task_type TEXT NOT NULL,
        lesson TEXT,
        task_data TEXT,
        status TEXT DEFAULT 'pending'
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS english_daily_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER DEFAULT 1,
        date TEXT NOT NULL,
        task_type TEXT NOT NULL,
        answers TEXT,
        score INTEGER,
        completed_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ── 插入默认孩子 ───────────────────────────────────────────
    cur.execute("INSERT OR IGNORE INTO child (id, name) VALUES (1, '小树')")

    # ── 插入勋章 ──────────────────────────────────────────────
    cur.executemany(
        "INSERT OR IGNORE INTO badges (badge_key, name, icon, condition, points) VALUES (?,?,?,?,?)",
        BADGES
    )

    # ── 插入字库 ──────────────────────────────────────────────
    for unit_id, unit_name, words_str in WORD_DATA:
        for word in words_str.split(","):
            word = word.strip()
            if not word:
                continue
            pinyin = get_pinyin(word)
            # 单字直接存 char，多字存 word
            if len(word) == 1:
                cur.execute(
                    "INSERT INTO words (char, pinyin, word, unit_id, unit_name) VALUES (?,?,NULL,?,?)",
                    (word, pinyin, unit_id, unit_name)
                )
            else:
                # 多字词：char 存词语本身，word 存 NULL（便于统一按 char 查询）
                cur.execute(
                    "INSERT INTO words (char, pinyin, word, unit_id, unit_name) VALUES (?,?,NULL,?,?)",
                    (word, pinyin, unit_id, unit_name)
                )

    conn.commit()
    conn.close()
    print(f"[init_db] ✅ 数据库创建完成 → {DB_PATH}")


if __name__ == "__main__":
    init()
