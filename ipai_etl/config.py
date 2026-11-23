import os
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(path=None):
    path = path or os.path.join(ROOT, "config.yaml")
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_root"] = os.path.dirname(os.path.abspath(path))
    for k, v in cfg["paths"].items():
        if not os.path.isabs(v):
            cfg["paths"][k] = os.path.join(cfg["_root"], v)
    for k in ("pdf_dir", "cache_dir", "output_dir"):
        os.makedirs(cfg["paths"][k], exist_ok=True)
    os.makedirs(os.path.dirname(cfg["paths"]["state_file"]), exist_ok=True)
    return cfg
