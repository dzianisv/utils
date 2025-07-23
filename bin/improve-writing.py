#!/usr/bin/env python3

from langchain_openai import ChatOpenAI
import sys
import os

llm = ChatOpenAI(openai_api_key=os.environ.get("OPENAI_API_KEY"))

def main():
    content = sys.stdin.read()
    output = llm.invoke(f"Proread the content inside <<< >>>, fix gramar mistakes and typos, make it funny to read software engineer post: <<<{content}>>>")
    print(output.content)

if __name__ == "__main__":
    main()