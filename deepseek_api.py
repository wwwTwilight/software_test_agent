# Please install OpenAI SDK first: `pip3 install openai`
import os
from openai import OpenAI

client = OpenAI(
    api_key='sk-f6fa8f0702464604a2cad39b4a95ccf2',
    base_url="https://api.deepseek.com")
while(1):
    Input = input("You: ")
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": Input},
        ],
        stream=False
    )

    print(response.choices[0].message.content)