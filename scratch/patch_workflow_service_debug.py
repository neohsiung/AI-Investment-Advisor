import re

with open('src/services/workflow_service.py', 'r') as f:
    text = f.read()

text = text.replace(
    "macro_deep = await macro_agent.run({})",
    """
        print(f"DEBUG type(macro_agent)={type(macro_agent)} macro_agent={macro_agent}")
        print(f"DEBUG type(macro_agent.run)={type(macro_agent.run)}")
        _res = macro_agent.run({})
        print(f"DEBUG type(_res)={type(_res)} _res={_res}")
        macro_deep = await _res
    """
)

with open('src/services/workflow_service.py', 'w') as f:
    f.write(text)
