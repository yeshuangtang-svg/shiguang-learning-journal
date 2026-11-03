"""Trusted bundled workflows; never load instructions from user-supplied paths."""
from pathlib import Path

NAMES = ('learning-document', 'visual-explanation', 'learning-review', 'formula-walkthrough',
         'concept-comparison', 'practice-coach', 'experiment-analysis', 'learning-roadmap')


def load_skill(name):
    if name not in NAMES:
        raise ValueError('请选择已安装的技能。')
    text = (Path(__file__).resolve().parent / 'skills' / name / 'SKILL.md').read_text(encoding='utf-8')
    header, instructions = text.split('---', 2)[1:]
    metadata = dict(line.split(':', 1) for line in header.strip().splitlines())
    return {'name': name, 'description': metadata['description'].strip(), 'instructions': instructions.strip()}


def skill_catalog():
    return [{key: value for key, value in load_skill(name).items() if key != 'instructions'} for name in NAMES]
