#!/usr/bin/env python3
# Start server `./llama-server -m Phi-3-mini-4k-instruct-q4.gguf --host 127.0.0.1 --port 8080`

import os
from langchain_openai import OpenAI
llm = OpenAI(openai_api_base=os.environ.get("LLAMACPP_API_ENDPOINT", "http://localhost:8080/"), openai_api_key="hello.world")
response = llm.invoke("write a python hello world")
print(response)