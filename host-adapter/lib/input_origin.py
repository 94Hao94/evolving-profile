"""Separate known adapter envelopes for intent/attachment classification.

This does not authenticate a human or change the original execution prompt.
"""
import re
import json

def user_surface_text(prompt: str) -> str:
    text=str(prompt or '')
    for tag in ('TRAINER_TRANSACTION_CONTEXT',):
        text=re.sub(rf'(?s)\[{tag}\].*?(?:\[/{tag}\]|$)', '', text)
    return text.strip()

def memory_query_text(prompt: str) -> str:
    """Use the human wording plus explicit lesson topic, not execution protocol."""
    text=str(prompt or '');surface=user_surface_text(text)
    if '[TRAINER_TRANSACTION_CONTEXT]' not in text:return surface
    block=text.split('[TRAINER_TRANSACTION_CONTEXT]',1)[1].split('[/TRAINER_TRANSACTION_CONTEXT]',1)[0]
    if '当前目标：' in block:
        try:
            target,_=json.JSONDecoder().raw_decode(block.split('当前目标：',1)[1].lstrip())
            topic=target.get('topic') if isinstance(target,dict) else None
            label=target.get('label') if isinstance(target,dict) else None
            context=[]
            if isinstance(topic,str) and topic.strip():context.append('练习主题：'+topic.strip())
            if isinstance(label,str) and label.strip():context.append('当前练习目标（不是历史事实）：'+label.strip())
            if context:return surface+'\n\n练习背景（服务提供，仅用于消解指代）：\n'+'\n'.join(context)
        except ValueError:pass
    return surface
