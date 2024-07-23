#!/usr/bin/env python3

from poept.langchain import PoeLLM
from langchain_core.prompts import PromptTemplate
import logging
import subprocess

logging.basicConfig(level=logging.INFO)

def main():
    llm = PoeLLM()
    proc = subprocess.run(['git', 'diff', 'origin/master...HEAD'], check=True, encoding='utf8')
    diff = proc.stdout

    template = """
Write a Github Pull Request description and title for the following git diff.
Keep it short and technical.

{diff}
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