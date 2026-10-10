import os
from pathlib import Path
import tempfile
# Never write test credentials or media to a real workspace.
os.environ['CLIPFORGE_DATA']=tempfile.mkdtemp(prefix='clipforge-tests-')
os.environ['LOCAL_TRUST']='0'
os.environ['WORKSPACE_TOKEN']='test-only-workspace-key'
