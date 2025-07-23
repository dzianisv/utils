#!/usr/bin/env python3

from langchain_openai import OpenAI
from langchain_core.prompts import PromptTemplate
import logging
import subprocess
import os

# logging.basicConfig(level=logging.INFO)

def main():
    llm = OpenAI(model='gpt-4o', openai_api_base=os.environ.get("OPENAI_API_BASE"), openai_api_key=os.environ.get("OPENAI_API_KEY"))
    
    # Check for the existence of 'master' or 'main' branch
    branches = subprocess.run(['git', 'branch', '-r'], stdout=subprocess.PIPE, check=True, encoding='utf8').stdout
    base_branch = 'origin/master' if 'origin/master' in branches else 'origin/main'
    
    proc = subprocess.run(['git', 'diff', f'{base_branch}...HEAD'], stdout=subprocess.PIPE, check=True, encoding='utf8')
    diff = proc.stdout

    template = """
1. Write a Github Pull Request
- description and
- title
for the following git diff.

```diff
{diff}
```

2. Write a JIRA ticket description.

3. Keep it short and technical. Output in Markdown.

"""

    prompt = PromptTemplate(
        template=template,
        input_variables=["diffs"]
    )

    chain = prompt | llm
    response = chain.invoke({"diff": diff})
    print(response)

if __name__ == "__main__":
    main()