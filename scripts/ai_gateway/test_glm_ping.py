#!/usr/bin/env python3
# Minimal GLM-only ping test. No key values printed. DeepSeek is NOT called.
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ai_gateway as g  # module import loads .env + vault keys (prints nothing)

rec = g.call('glm', 'ping')
print('provider=glm model=', 'glm-4.6' if 'GLM_MODEL' not in os.environ else os.environ['GLM_MODEL'])
print('status=', rec.get('status'))
print('latency_s=', rec.get('latency_s'))
eb = rec.get('error_body')
if eb:
    print('error_body_head=', eb[:120].replace('\n', ' '))
print('has_output=', 'output' in rec)
