#!/usr/bin/env python3

from poept.langchain import PoeLLM
from langchain_core.prompts import PromptTemplate
import logging
import subprocess

# logging.basicConfig(level=logging.INFO)

def main():
    llm = PoeLLM()
    proc = subprocess.run(['git', 'diff', 'origin/master...HEAD'], stdout=subprocess.PIPE, check=True, encoding='utf8')
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
    response = chain.invoke({"diff":diff})
    print(response)

if __name__ == "__main__":
    main()