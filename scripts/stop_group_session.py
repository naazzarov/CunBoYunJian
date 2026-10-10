"""Ask this workspace's group launcher to stop its own services cleanly."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
config_path = root / 'data/group-config.json'
config = json.loads(config_path.read_text()) if config_path.exists() else {}
data = Path(config.get('data', root / 'data')).resolve()
data.mkdir(parents=True, exist_ok=True)
(data / 'group.stop').touch()
print('Stop requested. / 已请求停止好友测试。')
