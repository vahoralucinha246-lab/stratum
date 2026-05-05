import os, json, uuid, re, random
from openai import OpenAI
from datetime import datetime
from collections import Counter

class EvolutionManager:
    def __init__(self, db_conn, config_path="config.json"):
        self.conn = db_conn
        self.config = self._load_config(config_path)
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("请设置环境变量 DEEPSEEK_API_KEY")
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = self.config.get("model", "deepseek-chat")

    def _load_config(self, path):
        try:
            with open(path) as f:
                return json.load(f)
        except:
            return {}

    def _chat(self, prompt, temp=0.5):
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role":"user","content":prompt}],
                temperature=temp
            )
            return resp.choices[0].message.content.strip()
        except:
            return "分析暂时不可用。"

    # ========== 核心方法（个人考古）==========
    def query_chain(self, keyword):
        atoms = self.conn.execute("SELECT subject, relation, object, confidence, sentiment, original_text, timestamp FROM atoms WHERE subject LIKE ? OR object LIKE ? ORDER BY timestamp ASC", (f"%{keyword}%", f"%{keyword}%")).fetchall()
        if not atoms: return "未找到相关观念原子。"
        timeline = [{"s":a[0],"r":a[1],"o":a[2],"c":a[3],"sent":a[4],"orig":a[5],"t":a[6]} for a in atoms]
        if len(timeline)==1:
            a=timeline[0]
            return f"仅记录到一次：{a['t']}\n{a['s']} {a['r']} {a['o']} (信心{a['c']},情感{a['sent']})\n原文：「{a['orig']}」"
        desc = "\n".join(f"{i+1}. [{a['t']}] {a['s']} {a['r']} {a['o']} (信心{a['c']},情感{a['sent']}) 原句:{a['orig']}" for i,a in enumerate(timeline))
        return self._chat(f"描述以下观念演化过程，指出强化/削弱/反转/细化。\n{desc}")

    def build_chains(self):
        groups = self.conn.execute("SELECT subject, object FROM atoms GROUP BY subject, object").fetchall()
        for subj, obj in groups:
            atoms = self.conn.execute("SELECT id, confidence, sentiment, original_text, timestamp FROM atoms WHERE subject=? AND object=? ORDER BY timestamp ASC", (subj, obj)).fetchall()
            if len(atoms)<2: continue
            for i in range(len(atoms)-1):
                a1,a2 = atoms[i], atoms[i+1]
                if self.conn.execute("SELECT id FROM chains WHERE atom_id1=? AND atom_id2=?", (a1[0],a2[0])).fetchone(): continue
                rel = self._chat(f"判断观念变化类型(intensified/weakened/reversed/refined/unchanged): A:{a1[3]}, B:{a2[3]}", temp=0.1)
                if rel not in ("intensified","weakened","reversed","refined","unchanged"): rel="unchanged"
                self.conn.execute("INSERT INTO chains (id, subject, object, atom_id1, atom_id2, relation_type, detected_at) VALUES (?,?,?,?,?,?,?)", (str(uuid.uuid4()), subj, obj, a1[0], a2[0], rel, datetime.now().isoformat()))
            self.conn.commit()

    def detect_pressure(self):
        atoms = self.conn.execute("SELECT subject, relation, object, sentiment FROM atoms ORDER BY timestamp DESC LIMIT 50").fetchall()
        if len(atoms)<4: return "数据不足。"
        desc = "\n".join(f"- {a[0]} {a[1]} {a[2]} (情感={a[3]:.1f})" for a in atoms)
        return self._chat(f"找出以下观念列表中的矛盾信念并解释冲突。如果没有，说‘未发现明显压力’。\n{desc}", temp=0.3)

    def infer_root_belief(self, user_input):
        return self._chat(f"推断这些观念背后共享的根基信念：‘{user_input}’。格式：根基信念：... 证据：...")

    def forecast(self):
        chains = self.conn.execute("SELECT subject, object, relation_type FROM chains ORDER BY detected_at DESC LIMIT 20").fetchall()
        atoms = self.conn.execute("SELECT subject, relation, object, sentiment FROM atoms ORDER BY timestamp DESC LIMIT 30").fetchall()
        if not chains and len(atoms)<5: return "数据不足。"
        c_desc = "\n".join(f"主题:{c[0]}-{c[1]} 关系:{c[2]}" for c in chains)
        a_desc = "\n".join(f"- {a[0]} {a[1]} {a[2]} (情感={a[3]:.1f})" for a in atoms[:15])
        return self._chat(f"基于以下数据，预测未来1-3个月用户可能出现的思想转变，3条，每条以‘你可能正在……’开头。\n演化链:\n{c_desc}\n近期观念:\n{a_desc}", temp=0.7)

    def generate_reflection_question(self, turns=10):
        traces = [r[0] for r in self.conn.execute("SELECT content FROM traces WHERE role='user' ORDER BY timestamp DESC LIMIT ?", (turns,)).fetchall()]
        if not traces: return None
        convo = "\n".join(f"- {t}" for t in reversed(traces))
        return self._chat(f"根据以下发音，生成一个引导反思的问题（只返回问题）。\n{convo}", temp=0.8)

    # 其它方法（省略重复，实际生成时会包含完整的mood、link、integrity...）
    def mood_analysis(self):
        atoms = self.conn.execute("SELECT timestamp, sentiment, subject, object FROM atoms ORDER BY timestamp ASC").fetchall()
        if not atoms: return "无情绪数据。"
        chart = "\n".join(f"{a[0][:10]}: {'+'*max(0,int(a[1]*10))}{'-'*max(0,int(-a[1]*10))} {a[2]}-{a[3]}" for a in atoms)
        analysis = self._chat(f"分析情绪趋势，指出关键高低点和触发事件。\n{chart}", temp=0.5)
        return f"--- 情绪地层图 ---\n{chart}\n\n{analysis}"

    # ========== 文本考古模块 ==========
    def load_corpus(self, filepath):
        if not os.path.exists(filepath): return f"文件不存在：{filepath}"
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS corpus (id TEXT PRIMARY KEY, name TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS corpus_entries (id TEXT PRIMARY KEY, corpus_id TEXT, content TEXT, entry_order INTEGER, timestamp TEXT, FOREIGN KEY (corpus_id) REFERENCES corpus(id));
            CREATE TABLE IF NOT EXISTS corpus_atoms (id TEXT PRIMARY KEY, entry_id TEXT, subject TEXT, relation TEXT, object TEXT, confidence INTEGER, sentiment REAL, original_text TEXT, timestamp TEXT, FOREIGN KEY (entry_id) REFERENCES corpus_entries(id));
        """)
        self.conn.commit()
        name = os.path.basename(filepath)
        cid = str(uuid.uuid4())
        self.conn.execute("INSERT INTO corpus (id, name, created_at) VALUES (?,?,?)", (cid, name, datetime.now().isoformat()))
        with open(filepath, 'r', encoding='utf-8') as f: text = f.read()
        blocks = re.split(r'\n\s*\n', text)
        blocks = [b.strip() for b in blocks if b.strip()]
        total = 0
        # 复用AtomExtractor
        from extractor import AtomExtractor
        extractor = AtomExtractor()
        for i, block in enumerate(blocks):
            eid = str(uuid.uuid4())
            ts = datetime.now().isoformat()
            m = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2})', block[:50])
            if m: ts = m.group(1)
            self.conn.execute("INSERT INTO corpus_entries (id, corpus_id, content, entry_order, timestamp) VALUES (?,?,?,?,?)", (eid, cid, block, i, ts))
            try:
                atoms = extractor.extract(block, ts)
                for a in atoms:
                    aid = str(uuid.uuid4())
                    self.conn.execute("INSERT INTO corpus_atoms (id, entry_id, subject, relation, object, confidence, sentiment, original_text, timestamp) VALUES (?,?,?,?,?,?,?,?,?)",
                                      (aid, eid, a.get('subject',''), a.get('relation',''), a.get('object',''), a.get('confidence',1), a.get('sentiment',0.0), a.get('original',''), ts))
                    total += 1
            except: pass
        self.conn.commit()
        return f"已导入《{name}》：{len(blocks)} 个段落，提取 {total} 个观念原子。"

    def list_corpora(self):
        rows = self.conn.execute("SELECT c.id, c.name, COUNT(e.id), (SELECT COUNT(*) FROM corpus_atoms ca JOIN corpus_entries ce2 ON ca.entry_id=ce2.id WHERE ce2.corpus_id=c.id) FROM corpus c LEFT JOIN corpus_entries e ON c.id=e.corpus_id GROUP BY c.id ORDER BY c.created_at DESC").fetchall()
        if not rows: return "尚未导入任何文本。"
        return "\n".join(f"  [{r[0][:8]}] 《{r[1]}》 {r[2]}段, {r[3]}个原子" for r in rows)

    def corpus_query_chain(self, keyword, corpus_name=None):
        if corpus_name:
            c = self.conn.execute("SELECT id FROM corpus WHERE name=?", (corpus_name,)).fetchone()
            if not c: return f"未找到文本：{corpus_name}"
            atoms = self.conn.execute("SELECT ca.subject, ca.relation, ca.object, ca.confidence, ca.sentiment, ca.original_text, ca.timestamp FROM corpus_atoms ca JOIN corpus_entries ce ON ca.entry_id=ce.id WHERE ce.corpus_id=? AND (ca.subject LIKE ? OR ca.object LIKE ?) ORDER BY ca.timestamp", (c[0], f"%{keyword}%", f"%{keyword}%")).fetchall()
        else:
            atoms = self.conn.execute("SELECT subject, relation, object, confidence, sentiment, original_text, timestamp FROM corpus_atoms WHERE subject LIKE ? OR object LIKE ? ORDER BY timestamp", (f"%{keyword}%", f"%{keyword}%")).fetchall()
        if not atoms: return "未找到相关观念。"
        timeline = [{"s":a[0],"r":a[1],"o":a[2],"c":a[3],"sent":a[4],"orig":a[5],"t":a[6]} for a in atoms]
        if len(timeline)==1:
            a=timeline[0]
            return f"仅出现一次：{a['t']}\n{a['s']} {a['r']} {a['o']} (信心{a['c']},情感{a['sent']})\n原文：「{a['orig']}」"
        desc = "\n".join(f"{i+1}. [{a['t']}] {a['s']} {a['r']} {a['o']} (信心{a['c']},情感{a['sent']}) 原句:{a['orig']}" for i,a in enumerate(timeline))
        return self._chat(f"描述以下文本观念演化过程，指出强化/削弱/反转/细化。\n{desc}")

    def corpus_compare(self, name1, name2):
        c1 = self.conn.execute("SELECT id FROM corpus WHERE name LIKE ?", (f"%{name1}%",)).fetchone()
        c2 = self.conn.execute("SELECT id FROM corpus WHERE name LIKE ?", (f"%{name2}%",)).fetchone()
        if not c1 or not c2: return "未找到其中一个文本。"
        atoms1 = self.conn.execute("SELECT ca.subject, ca.object FROM corpus_atoms ca JOIN corpus_entries ce ON ca.entry_id=ce.id WHERE ce.corpus_id=?", (c1[0],)).fetchall()
        atoms2 = self.conn.execute("SELECT ca.subject, ca.object FROM corpus_atoms ca JOIN corpus_entries ce ON ca.entry_id=ce.id WHERE ce.corpus_id=?", (c2[0],)).fetchall()
        set1 = set(f"{a[0]}-{a[1]}" for a in atoms1)
        set2 = set(f"{a[0]}-{a[1]}" for a in atoms2)
        common = set1 & set2
        only1 = set1 - set2
        only2 = set2 - set1
        prompt = f"比较两文本。共同观念：{common or '无'}；仅文本1：{only1 or '无'}；仅文本2：{only2 or '无'}。分析根基信念差异和冲突点。"
        return self._chat(prompt)
    # ========== 仪表盘数据 ==========
    def dashboard_data(self):
        # 统计
        atom_count = self.conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0]
        chain_count = self.conn.execute("SELECT COUNT(*) FROM chains").fetchone()[0]
        trace_count = self.conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        
        # 平均情绪
        avg_row = self.conn.execute("SELECT AVG(sentiment) FROM atoms WHERE sentiment IS NOT NULL").fetchone()
        avg_sentiment = avg_row[0] if avg_row[0] else 0
        
        # 情绪序列（最近30条）
        mood_series = []
        for row in self.conn.execute("SELECT timestamp, sentiment FROM atoms ORDER BY timestamp DESC LIMIT 30").fetchall():
            mood_series.append({"timestamp": row[0], "sentiment": row[1] if row[1] else 0})
        mood_series.reverse()
        
        # 正面/负面计数
        positive_count = self.conn.execute("SELECT COUNT(*) FROM atoms WHERE sentiment > 0").fetchone()[0]
        negative_count = self.conn.execute("SELECT COUNT(*) FROM atoms WHERE sentiment < 0").fetchone()[0]
        
        # 高频观念（subject-object 对）
        from collections import Counter
        pairs = self.conn.execute("SELECT subject, object FROM atoms").fetchall()
        counter = Counter((p[0], p[1]) for p in pairs if p[0] and p[1])
        hot_concepts = [{"subject": k[0], "object": k[1], "count": v} for k, v in counter.most_common(10)]
        
        # 最新演化链
        chains = []
        for row in self.conn.execute("SELECT subject, object, relation_type, detected_at FROM chains ORDER BY detected_at DESC LIMIT 10").fetchall():
            chains.append({
                "subject": row[0],
                "object": row[1],
                "relation_type": row[2],
                "detected_at": row[3]
            })
        
        return {
            "atom_count": atom_count,
            "chain_count": chain_count,
            "trace_count": trace_count,
            "avg_sentiment": avg_sentiment,
            "mood_series": mood_series,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "hot_concepts": hot_concepts,
            "recent_chains": chains
        }
