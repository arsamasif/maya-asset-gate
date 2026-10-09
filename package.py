name = "asset_gate"

version = "0.1.0"

authors = ["Arsam Ali"]

description = "Validate-then-publish gate for Maya assets, ending in a USD component asset."

requires = [
    "python-3.10+",
    "usd",
    "PyYAML",
]

tools = ["asset-gate"]


def commands():
    env.PYTHONPATH.append("{root}/python")
    alias("asset-gate", "python -m asset_gate")
