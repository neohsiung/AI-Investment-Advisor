import re

file_path = 'src/services/workflow_service.py'
with open(file_path, 'r') as f:
    text = f.read()

# Replace agent.run() with await agent.run()
text = re.sub(r'(?<!await )([a-zA-Z0-9_]+_agent|cio|engineer|agent)\.run\(', r'await \1.run(', text)

# Replace execute_analysis defs
text = re.sub(r'(?<!await )def execute_analysis\(self, force_refresh: bool\) -> bool:', r'async def execute_analysis(self, force_refresh: bool) -> bool:', text)
text = re.sub(r'(?<!async )def execute_analysis\(self, force_refresh: bool\) -> bool:', r'async def execute_analysis(self, force_refresh: bool) -> bool:', text)

# Replace execute_analysis calls
text = re.sub(r'(?<!await )self\.execute_analysis\(force_refresh\)', r'await self.execute_analysis(force_refresh)', text)

# Replace translation LLM call
text = re.sub(r'(?<!await )translator\._call_real_llm\(', r'await translator._call_real_llm(', text)

with open(file_path, 'w') as f:
    f.write(text)
print("Updated workflow_service.py")
