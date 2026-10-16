
path = r'c:\Users\pc\PycharmProjects\Court-Scraper\pipeline\base.py'
content = open(path, 'r', encoding='utf-8').read()

tracker_snippet = (
    '\n    # \u2500\u2500 Pipeline telemetry tracker (injected by orchestrator) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '    batch_name: str = ""\n'
    '    tracker:    Any = None  # PipelineTracker instance\n'
)

# Patch PipelineContext block_statuses anchor
anchor1 = '    block_statuses: dict = field(default_factory=dict)\n\n\n# \u2500\u2500 Per-case context for Florida'
replacement1 = '    block_statuses: dict = field(default_factory=dict)\n' + tracker_snippet + '\n\n# \u2500\u2500 Per-case context for Florida'

if anchor1 in content:
    content = content.replace(anchor1, replacement1, 1)
    print('PipelineContext: tracker injected OK')
else:
    print('PipelineContext anchor NOT found — raw snippet:')
    idx = content.find('block_statuses: dict = field')
    print(repr(content[idx-4:idx+120]))

# Patch FloridaPipelineContext block_statuses anchor
anchor2 = '    block_statuses: dict = field(default_factory=dict)\n\n\n# \u2500\u2500 Abstract block interface'
replacement2 = '    block_statuses: dict = field(default_factory=dict)\n' + tracker_snippet + '\n\n# \u2500\u2500 Abstract block interface'

if anchor2 in content:
    content = content.replace(anchor2, replacement2, 1)
    print('FloridaPipelineContext: tracker injected OK')
else:
    print('FloridaPipelineContext anchor NOT found')

open(path, 'w', encoding='utf-8').write(content)
print('Done. Total lines:', content.count('\n'))
