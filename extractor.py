import os, json
from openai import OpenAI

class AtomExtractor:
    def __init__(self):
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key: raise ValueError("请设置 DEEPSEEK_API_KEY")
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = "deepseek-chat"

    def extract(self, text, timestamp):
        prompt = f"提取以下句子的观念原子，返回JSON数组，每个对象含：subject,relation,object,confidence(1-5),sentiment(-1~1),original。没有就返回[]。输入：{text}"
        try:
            resp = self.client.chat.completions.create(model=self.model, messages=[{"role":"user","content":prompt}], temperature=0.1, response_format={"type":"json_object"})
            data = json.loads(resp.choices[0].message.content)
            if isinstance(data, list): return data
            if isinstance(data, dict) and "atoms" in data: return data["atoms"]
            return []
        except:
            return []

class MemoryResponder:
    def __init__(self):
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = "deepseek-chat"

    def find_similar(self, current_text, conn, threshold=0.3):
        cursor = conn.execute("SELECT content, timestamp FROM traces WHERE role='user' ORDER BY timestamp DESC LIMIT 100")
        best = None; best_sim = 0
        for row in cursor:
            if row[0] == current_text: continue
            sim = self._similarity(current_text, row[0])
            if sim > best_sim:
                best_sim = sim; best = row
        return best if best_sim >= threshold else None

    def _similarity(self, a, b):
        set_a, set_b = set(a), set(b)
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection)/len(union) if union else 0

    def generate_response(self, current_text, similar_text, similar_timestamp):
        prompt = f"你是Stratum，用户说：‘{current_text}’，想起他曾说过：‘{similar_text}’（{similar_timestamp}），生成一句回应，提及过去的话。"
        try:
            resp = self.client.chat.completions.create(model=self.model, messages=[{"role":"user","content":prompt}], temperature=0.7)
            return resp.choices[0].message.content.strip()
        except:
            return None
